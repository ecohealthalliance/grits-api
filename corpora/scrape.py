__version__ = '0.0.0'
import urllib2, httplib
import scrape_promed
import readability
import sys, exceptions, socket
import lxml
import datetime

class OpenURLHandler(urllib2.HTTPRedirectHandler):
    def http_request(self, request):
        request.add_header("User-agent", "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.154 Safari/537.36")
        return request
primary_opener = urllib2.build_opener(OpenURLHandler())

class BackupOpenURLHandler(urllib2.HTTPRedirectHandler):
    """
    Using add_unredirected_header avoids 403s on some sites.
    It seems to be an idiosyncracy of the way some sites are configured.
    More info here:
    http://stackoverflow.com/questions/23602996/why-does-setting-the-user-agent-in-an-unredirected-header-avoid-403s
    """
    def http_request(self, request):
        request.add_unredirected_header("User-agent", "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.154 Safari/537.36")
        return request
backup_opener = urllib2.build_opener(BackupOpenURLHandler())

def open_url(opener, url):
    try:
        res = opener.open(url, timeout=60)
        if res.getcode() >= 300:
            print res.getcode(), url
            return {
                'sourceUrl' : url,
                'unscrapable' : True,
                'exception' : str(res.getcode())
            }
        else:
            # TODO: Use an encoding detector.
            # Many Chinese pages are gb2312 encoded.
            html = res.read()
    except (urllib2.HTTPError, urllib2.URLError):
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'exception' : "URLLibError: Could not scrape url: " + errDescription
        }
    except (httplib.IncompleteRead, httplib.BadStatusLine):
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'exception' : "HTTPLibError: Could not scrape url: " + errDescription
        }
    except (socket.timeout, socket.error):
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'exception' : "SocketError:Could not scrape url: " + errDescription
        }
    except (UnicodeEncodeError, UnicodeDecodeError):
        # These errors might be surmountable
        # http://stackoverflow.com/questions/4389572/how-to-fetch-a-non-ascii-url-with-python-urlopen
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        ascii_url = url.encode('ascii', 'xmlcharrefreplace')
        print "UnicodeError:Could not scrape url: ", ascii_url
        return {
            'sourceUrl' : ascii_url,
            'unscrapable' : True,
            'exception' : errDescription
        }
    except exceptions.KeyboardInterrupt as e:
        raise e
    except:
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        print "Unknown error:Could not scrape url: ", url
        print errDescription
        raise Exception("Unknown error")
    if not html:
        print "Empty document at: " + url
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'parseException' : "Empty document"
        }
    else:
        return html

def scrape_main(url):
    if url.endswith('.pdf'):
        print "Could not scrape url because it is a PDF: " + url
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'exception' : "We can't scrape PDFs yet..."
        }
    parsed_url = None
    try:
        # Can this handle unicode urls?
        parsed_url = urllib2.urlparse.urlparse(url)
    except:
        raise Exception("urlparse exception")
    
    if not parsed_url or not parsed_url.hostname:
        print "Could not parse url: " + url
        return {
            'sourceUrl' : url,
            'unscrapable' : True
        }
    if 'promed' in parsed_url.hostname:
        return_value = scrape_promed.scrape_promed(url)
        return_value['sourceUrl'] = url
        return return_value
    if 'empres-i.fao.org' in parsed_url.hostname:
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'exception' : "We don't scrape empres-i reports."
        }
    if 'news.google.com' in parsed_url.hostname:
        parsed_qs = urllib2.urlparse.parse_qs(parsed_url.query)
        source_url = parsed_qs.get('url')[0]
        testparse = urllib2.urlparse.urlparse(source_url)
        if not testparse or not testparse.hostname:
            print url, "has a bad url parameter"
        if source_url:
            return scrape(source_url)
        else:
            print "Could not extract url parameter from: " + url
            return {
                'sourceUrl' : url,
                'unscrapable' : True
            }
    else:
        html_or_errordict = open_url(primary_opener, url)
        if isinstance(html_or_errordict, dict):
            html_or_errordict = open_url(backup_opener, url)
            if isinstance(html_or_errordict, dict):
                return html_or_errordict
        # HTML successfully fetched
        html = unicode(html_or_errordict, errors='replace')
        # I found out about goose and readability from here:
        # http://stackoverflow.com/questions/14164350/identifying-large-bodies-of-text-via-beautifulsoup-or-other-python-based-extract
        # The poster seems to like goose more, and what's really nice about it
        # is that it cleans up all the html.
        # However, this means it looses links and formatting.
        # Readability seems to just get rid of the cruft, so I'm using it here
        # because we can process it's output with Goose later on to get pure text.
        # Goose also has some nice metadata extraction features we might want to
        # look into in the future.
        readability_error = None
        try:
            document = readability.readability.Document(html)
            cleaner_content = document.summary()
            if len(cleaner_content) > 50:
                return {
                    'sourceUrl' : url,
                    'content' : cleaner_content
                }
            else:
                readability_error = "Readability content too short: " + cleaner_content
        except readability.readability.Unparseable as e:
            readability_error = '\n'.join([str(i) for i in sys.exc_info()])
        except (lxml.etree.XMLSyntaxError,
                lxml.etree.DocumentInvalid,
                lxml.etree.ParserError) as e:
            readability_error = '\n'.join([str(i) for i in sys.exc_info()])
        except (AttributeError, ValueError, TypeError) as e:
            # This ought to be handled by readability.
            readability_error = '\n'.join([str(i) for i in sys.exc_info()])
        except exceptions.KeyboardInterrupt as e:
            raise e
        except:
            readability_error = '\n'.join([str(i) for i in sys.exc_info()])
        
        return {
            'sourceUrl' : url,
            'unscrapable' : True,
            'parseException' : readability_error,
            'htmlContent' : html
        }

def scrape(url):
    scrape_time = datetime.datetime.now()
    result = scrape_main(url)
    result['scrapeDate'] = scrape_time
    result['scraperVersion'] = __version__
    return result
