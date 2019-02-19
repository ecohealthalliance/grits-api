"""
This script retrieves promed articles and parses their content.
"""
from __future__ import absolute_import
from __future__ import print_function
import re
import contextlib
import json
import time
import os
import requests
from urllib.parse import unquote
from urllib.parse import urlencode
import datetime
import dateutil.parser
from bs4 import BeautifulSoup
import disease_label_table
import lxml.html.soupparser


__version__ = '0.1.5'

# For some summary posts (ex: 2194235) communicated by seems to be a per
# article property, while in other posts it appears to be summary wide.
# For that reson this regex is used in multiple places
communicated_by_regex = r"^--?\s?\n\s?((Communicated|Reported) by\:\s?\n?)?\n*(?P<communicated_by>(.+\n)*(.+$))?"

TimeZoneStr = '''-12 Y
-11 X NUT SST
-10 W CKT HAST HST TAHT TKT
-9 V AKST GAMT GIT HADT HNY
-8 U AKDT CIST HAY HNP PST PT
-7 T HAP HNR MST PDT
-6 S CST EAST GALT HAR HNC MDT
-5 R CDT COT EASST ECT EST ET HAC HNE PET
-4 Q AST BOT CLT COST EDT FKT GYT HAE HNA PYT
-3 P ADT ART BRT CLST FKST GFT HAA PMST PYST SRT UYT WGT
-2 O BRST FNT PMDT UYST WGST
-1 N AZOT CVT EGT
0 Z EGST GMT UTC WET WT
1 A CET DFT WAT WEDT WEST
2 B CAT CEDT CEST EET SAST WAST
3 C EAT EEDT EEST IDT MSK
4 D AMT AZT GET GST KUYT MSD MUT RET SAMT SCT
5 E AMST AQTT AZST HMT MAWT MVT PKT TFT TJT TMT UZT YEKT
6 F ALMT BIOT BTT IOT KGT NOVT OMST YEKST
7 G CXT DAVT HOVT ICT KRAT NOVST OMSST THA WIB
8 H ACT AWST BDT BNT CAST HKT IRKT KRAST MYT PHT SGT ULAT WITA WST
9 I AWDT IRKST JST KST PWT TLT WDT WIT YAKT
10 K AEST ChST PGT VLAT YAKST YAPT
11 L AEDT LHDT MAGT NCT PONT SBT VLAST VUT
12 M ANAST ANAT FJT GILT MAGST MHT NZST PETST PETT TVT WFT
13 FJST NZDT
11.5 NFT
10.5 ACDT LHST
9.5 ACST
6.5 CCT MMT
5.75 NPT
5.5 SLT
4.5 AFT IRDT
3.5 IRST
-2.5 HAT NDT
-3.5 HNT NST NT
-4.5 HLV VET
-9.5 MART MIT'''
TimeZoneDict = {}


def getTimeZoneDict():
    """
    Timezones are often stored as abreviations such as EST.  These are
    ambiguous, but should still be handled.  See
    http://stackoverflow.com/questions/1703546
    :returns: a dictionary that can be passed to dateutil.parser.parse.
    """
    if not len(TimeZoneDict):
        for tz_descr in map(str.split, TimeZoneStr.split('\n')):
            tz_offset = int(float(tz_descr[0]) * 3600)
            for tz_code in tz_descr[1:]:
                TimeZoneDict[tz_code] = tz_offset
    return TimeZoneDict


def dom_tree_to_formatted_text(el):
    result = ""
    if not hasattr(el, "children"):
        normed_text = unicode(el).replace(u"\xa0", " ")
        # Make it so spaces are the only whitespace char and there is never
        # more than one in a row.
        return re.sub("\s\s+", " ", re.sub(r"\s", " ", normed_text, re.M))
    for child in el.children:
        if child.name and (re.match(r"h\d|p", child.name)):
            result = re.sub("( )+$", "", result)
            result += "\n" + dom_tree_to_formatted_text(child).strip() + "\n\n"
        elif str(child.name) == "br":
            result = re.sub("( )+$", "", result)
            result += "\n"
        else:
            if len(result) > 0 and re.match(r"\s", result[-1:]):
                result += dom_tree_to_formatted_text(child).lstrip()
            else:
                result += dom_tree_to_formatted_text(child)
    return result.strip()


def promed_html_to_formatted_text(html):
    """
    Convert HTML from the ProMED API into whitespace formatted text
    with the HTML tags removed.
    """
    # This is to fix some cases in malformed html where <s aren't esacaped.
    # >s can be parsed without escaping.
    normed_html = html.\
        replace("<<", "&lt;<").\
        replace("<http", "&lt;http").\
        replace("< ", "&lt; ")
    return dom_tree_to_formatted_text(BeautifulSoup(normed_html, "lxml"))


def parse_subject_line(txt):
    subject_re = re.compile(
        r"PRO(/(?P<ns1>\w{1,4}))?(/(?P<ns2>\w{1,4}))?\>" +
        r" (?P<description>.+?)" +
        r"( - (?P<region>\w[\w\s]*?\w" +
            # Sometimes a specific location is specified with the
            # region in a parenthetical section.
            r"( \(\D[\D\s]*?\w\))?" +
        r"))?" +
        r"( \((?P<threadNum>\d{1,3})\))?" +
        r"(: (?P<additionalInfo>.*))?" +
        r"$")
    match = subject_re.match(txt)
    if match:
        result = {
            k: v
            for k, v in match.groupdict().items()
            if v
        }
    else:
        # Try to parse an old style subject line
        match2 = re.match(r"PROMED: (?P<description>.+)", txt)
        if match2:
            result = match2.groupdict()
        else:
            result = {
                'description': txt,
                # If the subjectline does not begin with a ProMED tag
                # it is considered to be malformed.
                'isMalformed': True
            }
    if 'threadNum' in result:
        result['threadNum'] = int(result['threadNum'])

    tags = []
    # I have found that the summary/update tags are not very useful.
    # There is an important type of "update" post on promed that includes
    # multiple articles, and the words summary and update most frequently appear
    # in the titles of these posts, however they often do not appear in the
    # title and they may appear in different types of posts.
    # Ex: http://www.promedmail.org/direct.php?id=474570
    if re.search(r"summary", txt, re.I):
        tags.append("summary")
    if re.search(r"update", txt, re.I):
        tags.append("update")
    # RFI/corr./correction tags seem to always be in additional info.
    # The full subject line is searched just in case it is not.
    if re.search(r"\bRFI\b|request for information", txt, re.I):
        tags.append("rfi")
    if re.search(r"corr\.|correction", txt, re.I):
        tags.append("correction")
    if re.search(r"announcement", txt, re.I):
        tags.append("announcement")
    # unknown/unidentified can refer to other things, like host,
    # so they have a more specific regex.
    if re.search(r"((unknown|unidentified) (illness|disease))|undiagnosed",
                 result["description"],
                 re.I):
        tags.append("undiagnosed")
    tags.sort()
    result['tags'] = tags

    result['diseaseLabels'] = []

    def simplify_text(s):
        return s.replace("&", "and").replace(",", "")

    for row in disease_label_table.get_table():
        for syn in row.get("synonyms", []) + [row["label"]]:
            if re.search(r"\b" + re.escape(simplify_text(syn)) + r"\b",
                         simplify_text(result["description"]), re.I):
                result['diseaseLabels'].append(row["label"])
                break
    return result


def parse_datetime(timestamp_txt):
    """
    Parse the given text as a datetime or return None if it cannot be parsed.
    """
    # The datestring is uppercased because the parser cannot handle
    # lowercase timezones.
    timestamp_txt = timestamp_txt.upper().strip()
    # Replace date ranges of the form 2-8 Jun 2014 with the last date in the range.
    # Example article: http://www.promedmail.org/direct.php?id=2539532
    # http://daterangeparser.readthedocs.org/ is not used because it can cause
    # problems when other formats are used. For example, if the year is not
    # included in the range the current year will be used.
    timestamp_txt = re.sub(r"\b\d{1,2}\-(\d{1,2}\s\w{3,10}\s\d{4})\b", r"\1", timestamp_txt)
    # A few timestamps have this format. The timezones are removed
    # and the offset is used instead.
    timestamp_txt = re.sub(r"CST(\-?\d)CDT$", r"\1", timestamp_txt)
    # If an offset is specified the timezone is removed because having
    # both can cause the parser to fail.
    timestamp_txt = re.sub(r"(\-\d{1,4})\s?[A-Z]{1,5}$", r"\1", timestamp_txt)
    # The parser fails on some date abbreviations.
    timestamp_txt = re.sub(r"\bthurs?\b", "Thursday", timestamp_txt, flags=re.I)
    timestamp_txt = re.sub(r"\btues\b", "Tuesday", timestamp_txt, flags=re.I)
    timestamp_txt = re.sub(r"\bweds\b", "Wednesday", timestamp_txt, flags=re.I)
    timestamp_txt = re.sub(r"\bsept\b", "September", timestamp_txt, flags=re.I)
    timestamp_txt = re.sub(r"(\w+)\s(\/\s[a-z]+)", r"\1", timestamp_txt, flags=re.I)
    # Check for malformed date formats that we know about.
    if re.search(r"\-\d{3}(\d{2,})?$", timestamp_txt):
        # timestamps with timezone offsets of a certain number of digits
        # cannot be parsed.
        return None
    if re.search(r"\s:", timestamp_txt):
        # timestamps with spaces before colons are not wellformed.
        return None

    try:
        date = dateutil.parser.parse(
            timestamp_txt,
            tzinfos=getTimeZoneDict(),
            default=datetime.datetime(9999, 1, 1))
        if date.year >= 9999:
            # The default year was used so the year was missing from the string.
            print("Missing year in date:", timestamp_txt.encode('ascii', 'xmlcharrefreplace'))
            return None
        else:
            return date
    except ValueError as e:
        print("Unexpected malformed date:", timestamp_txt.encode('ascii', 'xmlcharrefreplace'))
        return None


def datetime_to_utc(dt):
    """
    Convert a timezone relative datetime a to non-relative utc datetime.
    """
    if dt.tzinfo:
        # Reduce [24, 48) hour offsets.
        if dt.tzinfo._offset >= datetime.timedelta(1):
            dt.tzinfo._offset -= datetime.timedelta(1)
            dt += datetime.timedelta(1)
        elif dt.tzinfo._offset <= datetime.timedelta(-1):
            dt.tzinfo._offset += datetime.timedelta(1)
            dt -= datetime.timedelta(1)
    return datetime.datetime(*dt.utctimetuple()[:6])


def parse_promed_pub_datetime(date_str):
    """
    Parse the date string assuming the US eastern time zone and return
    a UTC datetime object.
    I am guessing that promed published dates are given in eastern times
    based on some experiments.
    """
    # hack to handle spaces being added to dates during translation
    date_str = date_str.replace(": ", ":")
    pub_date = parse_datetime(date_str)
    # Aproximate whether to use DST timezones
    daylight_savings = parse_datetime("3/8/%s" % pub_date.year) <= pub_date
    daylight_savings &= parse_datetime("11/1/%s" % pub_date.year) >= pub_date
    tz = "EDT" if daylight_savings else "EST"
    tz_relative_date = parse_datetime(date_str + " " + tz)
    return datetime_to_utc(tz_relative_date)


def parse_article_text(article_text, post_date=datetime.datetime.now()):
    """
    Parse the content of an article embedded in a promed mail post.
    Currently, an article in considered to be a block of text, delimited
    by lines of #s or similar characters, with a Date and/or Source heading.
    This leaves out a few of types of post content such as:
    Emails:
    http://www.promedmail.org/direct.php?id=2194235
    http://www.promedmail.org/direct.php?id=19950210.0054
    Quotes from discussion boards:
    http://www.promedmail.org/direct.php?id=19950330.0170
    Short summaries:
    http://www.promedmail.org/direct.php?id=20131223.2132849
    """
    result = {}
    metadata_start = 0
    main_content_start = 0
    main_content_end = len(article_text)

    article_date_match = re.search(r"^Date:\s(?P<date>[^\(\[\n\`]+)", article_text, re.M | re.I)
    if article_date_match:
        # There may be more than one source date in summary articles.
        # Example: http://promedmail.org/direct.php?id=1073176
        # Summary articles are not a focus so currently only the first date
        # is recorded.
        source_date = parse_datetime(
            article_date_match.group("date")
        )

        if source_date:
            result["date"] = datetime_to_utc(source_date)
            metadata_start = min(article_date_match.start(), metadata_start)
            main_content_start = max(article_date_match.end(), main_content_start)
            # The year is checked to avoid typos like 200_ that throw
            # the date off by a large factor.
            # Example: http://www.promedmail.org/direct.php?id=45850 (article 2)
            if result["date"].year < 1900:
                result["date"] = None
            # Some articles have timestamps that are incorrectly parsed.
            # Current examples:
            # http://www.promedmail.org/direct.php?id=43918
            # http://www.promedmail.org/direct.php?id=2200173
            # Some of these incorrect timestamps can be removed by verifying that
            # they preceed the time of the posting. A day of slop time is allowed
            # to account for variations due to incorrect timezones.
            elif result["date"] > post_date + datetime.timedelta(1):
                result["date"] = None
        else:
            result["date"] = None

    source_match = re.search(r"Source:\s(?P<name>[^\[\n]+)" +
                             r"(\s(?P<edits>\[.*))?" +
                             r"\n" +
                             r"(?P<url>http.+)?", article_text)

    if source_match:
        result["source"] = source_match.groupdict()
        metadata_start = min(source_match.start(), metadata_start)
        main_content_start = max(source_match.end(), main_content_start)

    heading_match = re.search(r"^(?P<idx>\[\d\]\s)?" +
                              r"(?P<heading>\S+.*)\n",
                              article_text[0:metadata_start], re.M)
    if heading_match:
        result["heading"] = heading_match.group("heading")

    communicated_match = re.search(communicated_by_regex, article_text, re.M)
    if communicated_match:
        result["communicatedBy"] = communicated_match.group("communicated_by")
        main_content_end = min(communicated_match.start(), main_content_end)

    result["content"] = article_text[main_content_start:main_content_end].strip()
    return result


def parse_post_metadata(post_text):
    """
    This parses promed post metadata such as the subject line, publication date
    and archive number.
    """
    result = {}

    header_end = 0

    promed_date_match = re.search(
        r"(Published Date|Date Published):\s(?P<date>.*)", post_text)
    result["promedDate"] = parse_promed_pub_datetime(
        promed_date_match.group("date"))
    archive_match = re.search(r"Archive Number(\s)?: (?P<num>.*)", post_text, re.IGNORECASE)
    result["archiveNumber"] = archive_match.group("num").strip()
    header_end = archive_match.end()

    subject = re.search(r"Subject:\s(?P<subject>.*)", post_text).group("subject")
    result["subject"] = parse_subject_line(subject)
    result["subject"]["raw"] = subject

    # This will not find all linked reports.
    # Some older posts refrence posts using different indexes I do not know
    # how to interpret.
    # Example: http://promedmail.org/direct.php?id=2194235
    result["linkedReports"] = [
        report_id for report_id in re.findall(r"\d{8}\.\d+", post_text)]

    # Most links will be article source urls or links to promed.
    result["links"] = list(set(
        re.findall(r"http\S+[^(\.\])(\.\)>\s]", post_text)))
    result["links"].sort()

    communicated_match = re.search(communicated_by_regex, post_text, re.M)
    if communicated_match:
        result["communicatedBy"] = communicated_match.group("communicated_by")
    return result, header_end


def parse_see_also(content):
    parts = re.split(r"^see also\s*\:?$", content, flags=re.M | re.I)
    if len(parts) > 1:
        return parts[0], [
            report_id for report_id in re.findall(r"\d{8}\.\d+", parts[1])]
    else:
        return parts[0], []


def parse_post_text(formatted_content, language='en'):
    """
    Parse formatted promed post test into a dictionary with the structured
    data that could be extracted from the post.
    """
    post = {
        'sourceLanguage': language
    }
    # Parse Mod comments and remove them from the text.
    potential_comments = re.finditer("\[.+?\]", formatted_content, re.DOTALL)
    comments = []
    for comment_match in potential_comments:
        comment = comment_match.group()
        mod = re.search(r"\-\s?Mod[\.\s]{1,2}(?P<mod>\w+\b)", comment)
        if mod:
            comments.append({
                "comment": comment,
                "mod": mod.group("mod")
            })
    post["modComments"] = comments

    # Comments are removed from the post test so that
    # links, reports, etc. mentioned by mods are not extracted.
    no_comment_txt = formatted_content
    for comment in comments:
        no_comment_txt = no_comment_txt.replace(comment["comment"], "")
    metadata, header_end = parse_post_metadata(no_comment_txt)
    post.update(metadata)

    sections = re.split(r"^[\*#]{3,}\s*$", no_comment_txt[header_end:], flags=re.M)
    if language != 'en':
        sections = [translate_to_english(language, s) for s in sections]

    articles = []

    # Some posts have articles which are parsed into multiple sections:
    # Ex: http://www.promedmail.org/direct.php?id=2194235
    # The section parsing code tries to recombine these by concatenating
    # unrecognized sections onto the previous sections if they form an article.
    # article_start_idx keeps track of the first section in the article.
    article_start_idx = None

    for idx, section in enumerate(sections):
        section = section.strip()
        section, see_also_links = parse_see_also(section)
        if len(see_also_links) > 0:
            post['seeAlsoLinks'] = see_also_links
        article = parse_article_text(section, post_date=post['promedDate'])
        # Check if the section contains an actual article by seeing which
        # properties could be parsed.
        if article.get('source') or article.get('date'):
            articles.append(article)
            article_start_idx = idx
        else:
            # When a section cannot be parsed as an article the following code
            # tries to determine what it is. If the type cannot be determined
            # an error or warning is thrown.
            # These warnings can be used to find sections which are not being
            # correctly parsed.
            # Posts with known issues:
            # http://www.promedmail.org/direct.php?id=19990512.0773
            if re.search(r"Visit ProMED-mail\'s web site at|"
                         r"Please support (the \d{4}\s)?ProMED\-mail|"
                         r"Donate to ProMED\-mail. Details available at|"
                         r"ProMED\-mail makes every effort to verify the reports|"
                         r"PROMED\-MAIL FREQUENTLY ASKED QUESTIONS|"
                         r"Become a( ProMED\-mail)? Premium Subscriber|"
                         r"A ProMED\-mail post|"
                         r"Visit the website of ProMED-mail|"
                         r"Send all items for posting on the PRO",
                         section, re.I):
                # boilerplate promed notice section
                pass
            elif re.search(r"In this (update|post(ing)?)", section):
                # table of contents section
                pass
            elif re.search(r"Cases in various countries", section):
                # This type of post typically has links to several articles
                # with single sentence summaries.
                # Ex: http://www.promedmail.org/direct.php?id=20131125.2073661
                pass
            elif section == "":
                # empty section
                pass
            elif idx == 0 and section.count("\n") < 2:
                # probably the article title
                pass
            else:
                if article_start_idx is not None:
                    article = parse_article_text(
                        "\n#####\n".join(
                            sections[article_start_idx:idx]).strip(),
                        post_date=post['promedDate'])
                    assert article.get('source') or article.get('date')
                    articles[-1] = article
                    continue
                else:
                    print("Unexpected Section (%s):" % post['archiveNumber'], [section[0:50] + "..."])
            article_start_idx = None
    post['articles'] = articles
    return post

# globals variables used by google translation
# to avoid exceeding the rate limit.
CHARS_PER_100_SEC = 100000
last_translation_time = datetime.datetime.now()
remaining_char_buffer = CHARS_PER_100_SEC


def translate_using_ms(text):
    full_text = ""
    url = "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&to=en"
    # Break text into 5000 character chunks to stay under api limit
    for section, noop in re.findall(r"(.{1,4500}(\s|$))", text, re.M | re.DOTALL):
        response = requests.post(url, headers={
            "Ocp-Apim-Subscription-Key": os.environ.get("MS_TRANSLATE_KEY"),
            "Content-type": "application/json",
        }, json=[{
            "Text" : section.encode("utf-8"),
        }])
        if response.status_code != requests.codes.ok:
            print(section.encode("utf-8"))
            print(response.content)
            response.raise_for_status()
        resp_json = response.json()
        resp_text = resp_json[0]["translations"][0]["text"]
        full_text += resp_text
    return full_text


def translate_chunk_using_google(text, language):
    global last_translation_time
    global remaining_char_buffer
    if remaining_char_buffer < len(text):
        print("Sleeping to avoid going above API limit...")
        # 25 seconds is a long enough delay to ensure the max text size of
        # 5000 characters can be translated without going over the
        # 20,000 chars / 100 seconds API limit.
        time.sleep(25)
    seconds_since_last_request = (datetime.datetime.now() - last_translation_time).seconds
    remaining_char_buffer = min(
        CHARS_PER_100_SEC,
        remaining_char_buffer + seconds_since_last_request * CHARS_PER_100_SEC / 100)
    url = "https://www.googleapis.com/language/translate/v2"

    params = {
        "target": "en",
        "key": translate_key,
        "source": language,
        "q": text
    }
    response = requests.get(url, params=params, verify=False)
    try:
        response_json = response.json()
    except Exception as e:
        print("response:", response.text)
        raise Exception("GTranslate API Error: " + response.text)
    remaining_char_buffer -= len(text)
    last_translation_time = datetime.datetime.now()
    if response_json.get("error"):
        if response_json["error"].get("message") == "Backend Error":
            print("GTranslate Backend Error. Retrying translation in 25 seconds...")
            time.sleep(25)
            return translate_chunk_using_google(text, language)
        else:
            print("response: " + response.text)
            raise Exception("GTranslate API Error: " + response.text)
    else:
        return response_json["data"]["translations"][0]["translatedText"] + " "


def translate_using_google(text, language):
    # The API is limited to 5000 characters
    # The text is broken into chunks smaller than that because when characters
    # are replaced the escaped versions may take up more space.
    chunked_text = re.findall(r"(.{1,1400}(\s|$))", text, re.M | re.DOTALL)
    output = ""
    for chunk in chunked_text:
        chunk_text = chunk[0]
        if re.match(r"^\s*$", chunk_text):
            output += chunk_text
            continue
        # strip newlines because URL encoding will do that anyway,
        # but we need a place holder determine line breaks when extracting dates
        chunk_text = chunk_text.replace('\n', '<br>')
        if isinstance(chunk_text, unicode):
            chunk_text = chunk_text.encode('utf-8', errors='backslashreplace')
        try:
            output += translate_chunk_using_google(chunk_text, language) + " "
        except Exception as e:
            print('problem translating article', e)
            print('text to be translated:', chunk_text)
            # bubble exception up so we can send a single email with all errors
            raise Exception(str(e), chunk_text)
    # The translation service is adding some uneeded characters in it's results. 
    # This is causing problems when parsing later so stripping out here:
    output = output.replace("Archive Number:..", "Archive Number:")
    output = output.replace("Reported by:.", "Reported by:")
    output = output.replace('<br>', '\n')
    # gtranslate sometimes inserts zero width spaces which can cause havoc.
    output = output.replace(u"\u200B", u"")
    clean_output = ""
    for line in output.split('\n'):
        clean_output += line.strip() + '\n'
    clean_output = lxml.html.soupparser.unescape(clean_output)
    return clean_output


def translate_to_english(language, text):
    return translate_using_ms(text)


def scrape_promed_id(_id, language='en'):
    """
    Fetch the ProMED post with the given id and parse its content to extract
    metadata such as the disease the post is about, whether the post is an
    update/RFI/Summary/etc., the urls mentioned, and the other posts
    mentioned.
    """
    url = "http://www.promedmail.org/ajax/getPost.php?alert_id=%s" % _id
    resp = requests.get(url, headers={"Referer": "http://www.promedmail.org/"})
    content = resp.json()
    zoomLat = content.get('zoom_lat')
    zoomLon = content.get('zoom_lon')
    zoomLevel = content.get('zoom_level')
    post_html = content.get('post')
    try:
        post_html = unquote(post_html)
    except Exception as e:
        print("Error decoding %s: %s" % (_id, e))

    formatted_content = promed_html_to_formatted_text(post_html)
    if len(formatted_content) < 88:
        # Non-existant posts return a page that just have the meta-data
        # headers, so if the content is less than the length of the headers
        # we have an empty post.
        return None
    result = {
        'promedScraperVersion': __version__,
        'content': formatted_content,
        'promedId': _id,
        'htmlContent': post_html,
        'zoomLat': zoomLat,
        'zoomLon': zoomLon,
        'zoomLevel': zoomLevel,
        'scrapeDate': datetime.datetime.now()
    }
    result.update(parse_post_text(formatted_content, language))
    return result


def scrape_promed_url(url):
    """
    Scrape the ProMED article with the given URL
    """
    article_id_regex = re.compile('id=(?P<id>\d+\.?\d*)')
    parse = article_id_regex.search(url)
    if parse:
        return scrape_promed_id(parse.groupdict().get('id'))
    else:
        raise Exception("Couldn't scrape url: " + url)