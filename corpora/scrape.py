__version__ = '0.0.1'
import urllib2, httplib
import chardet
import httplib2
import scrape_promed
import readability
import sys, exceptions, socket
import lxml
import datetime

class OpenURLHandler(urllib2.HTTPRedirectHandler):
    def http_request(self, request):
        request.add_header("User-agent", "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.154 Safari/537.36")
        return request
    def http_error_301(self, req, fp, code, msg, headers):  
        result = urllib2.HTTPRedirectHandler.http_error_301(
            self, req, fp, code, msg, headers)
        if not hasattr(result, 'redirects'):
            result.redirects = []
        result.redirects.append({
            'url' : req.get_full_url(),
            'code' : code
        })
        return result
    def http_error_302(self, req, fp, code, msg, headers):
        result = urllib2.HTTPRedirectHandler.http_error_302(
            self, req, fp, code, msg, headers)
        if not hasattr(result, 'redirects'):
            result.redirects = []
        result.redirects.append({
            'url' : req.get_full_url(),
            'code' : code
        })
        return result
primary_opener = urllib2.build_opener(OpenURLHandler())

class BackupOpenURLHandler(OpenURLHandler):
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
    url = httplib2.iri2uri(url)
    result = {
        'sourceUrl' : url
    }
    try:
        resp = opener.open(url, timeout=60)
        if hasattr(resp, 'redirects'):
            result['redirects'] = resp.redirects
        result['code'] = resp.code
        result['msg'] = resp.msg
        result['url'] = resp.url
        if resp.getcode() >= 300:
            result['unscrapable'] = True
            return result
        else:
            html = resp.read()
            if not html:
                result.update({
                    'unscrapable' : True,
                    'exception' : "No html returned"
                })
                return result
            result['htmlContent'] = unicode(
                html.decode(encoding=chardet.detect(html)['encoding']),
            )
            return result
    except (urllib2.HTTPError, urllib2.URLError):
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        result.update({
            'unscrapable' : True,
            'exception' : "URLLibError: Could not scrape url: " + errDescription
        })
        return result
    except (httplib.IncompleteRead, httplib.BadStatusLine):
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        result.update({
            'unscrapable' : True,
            'exception' : "HTTPLibError: Could not scrape url: " + errDescription
        })
        return result
    except (socket.timeout, socket.error):
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        result.update({
            'unscrapable' : True,
            'exception' : "SocketError:Could not scrape url: " + errDescription
        })
        return result
    except (UnicodeEncodeError, UnicodeDecodeError):
        # I think using iri2uri will prevent this
        # http://stackoverflow.com/questions/4389572/how-to-fetch-a-non-ascii-url-with-python-urlopen
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        result.update({
            'unscrapable' : True,
            'exception' : errDescription
        })
        return result
    except exceptions.KeyboardInterrupt as e:
        raise e
    except:
        errDescription = '\n'.join([str(i) for i in sys.exc_info()])
        print "Unknown error:Could not scrape url: ", url
        print errDescription
        raise Exception("Unknown error")

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
        result = open_url(primary_opener, url)
        if result.get('unscrapable'):
            result = open_url(backup_opener, url)
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
            document = readability.readability.Document(result['htmlContent'])
            cleaner_content = document.summary()
            if len(cleaner_content) > 50:
                result.update({
                    'content' : cleaner_content
                })
                return result
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
        result.update({
            'unscrapable' : True,
            'exception' : "ReadabilityError: " + readability_error
        })
        return result

def scrape(url):
    scrape_time = datetime.datetime.now()
    result = scrape_main(url)
    result['scrapeDate'] = scrape_time
    result['scraperVersion'] = __version__
    return result
