import re
import datetime
import pattern.search, pattern.en
import itertools

def parse_spelled_number(tokens):
    numbers = {
        'zero':0,
        'half': 1.0/2.0,
        'one':1,
        'two':2,
        'three':3,
        'four':4,
        'five':5,
        'six':6,
        'seven':7,
        'eight':8,
        'nine':9,
        'ten':10,
        'eleven':11,
        'twelve':12,
        'thirteen':13,
        'fourteen':14,
        'fifteen':15,
        'sixteen':16,
        'seventeen':17,
        'eighteen':18,
        'nineteen':19,
        'twenty':20,
        'thirty':30,
        'forty':40,
        'fifty':50,
        'sixty':60,
        'seventy':70,
        'eighty':80,
        'ninety':90,
        'hundred':100,
        'thousand':1000,
        'million': 1000000,
        'billion': 1000000000,
        'trillion':1000000000000,
        'gillion' :1000000000,
    }
    punctuation = re.compile(r'[\.\,\?\(\)\!]')
    affix = re.compile(r'(\d+)(st|nd|rd|th)')
    def clean_token(t):
        t = punctuation.sub('', t)
        t = affix.sub(r'\1', t)
        return t.lower()
    def parse_token(t):
        try:
            return int(t)
        except ValueError:
            try:
                return float(t)
            except ValueError:
                if t in numbers:
                    return numbers[t]
                else:
                    return t
    cleaned_tokens = [clean_token(t) for t in tokens if t not in ['and', 'or']]
    numeric_tokens = map(parse_token, cleaned_tokens)
    if any(filter(lambda t: isinstance(t, basestring), numeric_tokens)) or len(numeric_tokens) == 0:
        print 'Error: Could not parse number: ' + unicode(tokens)
        return
    number_out = 0
    idx = 0
    while idx < len(numeric_tokens):
        cur_t = numeric_tokens[idx]
        next_t = numeric_tokens[idx + 1] if idx + 1 < len(numeric_tokens) else None
        if next_t and cur_t < next_t:
            number_out += cur_t * next_t
            idx += 2
            continue
        number_out += cur_t
        idx += 1
    return number_out

my_taxonomy = None

def extract_counts(text):
    global my_taxonomy
    if not my_taxonomy:
        my_taxonomy = pattern.search.Taxonomy()
        my_taxonomy.append(pattern.search.WordNetClassifier())
    #Case counts
    tree = pattern.en.parsetree(text, lemmata=True)
    matches = pattern.search.search('{CD+ CC? CD?} NP? PATIENT|CASE|INFECTION', tree, taxonomy=my_taxonomy)
    #Ex: it brings the number of cases reported in Jeddah since 27 Mar 2014 to 28
    #Ex: The number of cases has exceeded 30
    matches += pattern.search.search('NUMBER OF PATIENT|CASE|INFECTION *? *? *? *? *? *? *? (VP|TO) {CD+ CC? CD?}', tree, taxonomy=my_taxonomy)
    matches += pattern.search.search('DEATHS :? {CD+}', tree, taxonomy=my_taxonomy)
    for m in matches:
        n = parse_spelled_number([s.string for s in m.group(1)])
        if n is not None:
            yield {
                'type' : 'caseCount',
                'value' : n,
                'text' : m.string
            }
    #Hospitalizations
    matches = pattern.search.search('{CD+ CC? CD?} NP? HOSPITALIZED', tree, taxonomy=my_taxonomy)
    #Ex: 222 were admitted to hospitals with symptoms of diarrhea
    matches += pattern.search.search('{CD+ CC? CD?} NP? VP TO? HOSPITAL', tree, taxonomy=my_taxonomy)
    for m in matches:
        n = parse_spelled_number([s.string for s in m.group(1)])
        if n is not None:
            yield {
                'type' : 'hospitalizationCount',
                'value' : n,
                'text' : m.string
            }
    #Deaths
    matches = pattern.search.search('{CD+ CC? CD?} NP? DIED|DEATHS|FATALITIES|KILLED', tree, taxonomy=my_taxonomy)
    matches += pattern.search.search('DEATHS :? {CD+}', tree, taxonomy=my_taxonomy)
    for m in matches:
        n = parse_spelled_number([s.string for s in m.group(1)])
        if n is not None:
            yield {
                'type' : 'deathCount',
                'value' : n,
                'text' : m.string
            }

def extract_dates(text):
    # I tried this package but the results weren't great.
    # https://code.google.com/p/nltk/source/browse/trunk/nltk_contrib/nltk_contrib/timex.py
    # I also tried HeidelTime, but I don't think it provides enough of an improvement
    # to make up for the added dependencies (Java, GPL). 
    # The nice the about HeidelTime is that it extracts a lot of additional information.
    # For instance, it can extract intervals and vague time references like "currently" or "recently". 
    def maybe(text_re):
        return r"(" + text_re + r")?"
    monthnames = "january february march april may june july august september october november december".split(" ")
    monthabrev = [s.lower() for s in "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")]
    month_re_str = r"(?P<monthname>" + '|'.join(monthnames) + r")"
    month_abrev_re_str = r"(?P<monthabrev>" + '|'.join(monthabrev) + r")"
    day_re_str = r"(?P<day>\d{1,2})(st|nd|rd|th)?"
    year_re_str = r"(?P<year>\d{4})"
    promed_body_date_re = re.compile(r"\b" + day_re_str + r"\s(" + month_re_str + r'|' +
        month_abrev_re_str + r")\s" + year_re_str + r"\b", re.I | re.M)
    promed_publication_date_re = re.compile(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2}) (?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})", re.I)
    mdy_date_re = re.compile(r"\b" + month_re_str +
        maybe(r'\s' + day_re_str) + maybe(r'\s' + year_re_str) + r"\b", re.I | re.M)
    #dmy_date_re = re.compile(r"\b" + day_re_str + r'\s' + month_re_str + r'\s' + year_re_str + r"\b", re.I | re.M)
    date_info_dicts = []
    matches = []
    for match in itertools.chain( promed_body_date_re.finditer(text),
                                  mdy_date_re.finditer(text),
                                  promed_publication_date_re.finditer(text)
                                ):
        date_info = {}
        for k, v in match.groupdict().items():
            if v is None: continue
            v = v.lower()
            if k == 'monthabrev':
                date_info['month'] = monthabrev.index(v) + 1
            elif k == 'monthname':
                date_info['month'] = monthnames.index(v) + 1
            else:
                date_info[k] = int(v)
        date_info_dicts.append(date_info)
        matches.append(match)
    probable_year = datetime.datetime.now().year
    years = [d['year'] for d in date_info_dicts if 'year' in d]
    if len(years) > 0:
        probable_year = int(sum(years) / len(years))
    for date_info, match in zip(date_info_dicts, matches):
        datetime_args = {'day':1, 'year':probable_year}
        datetime_args.update(date_info)
        try:
            value = datetime.datetime(**datetime_args)
            yield {
                'type' : 'datetime',
                'dateInformation' : date_info,
                'value' : datetime.datetime(**datetime_args),
                'startOffset' : match.start(),
                'endOffset' : match.end(),
                'text' : text[match.start():match.end()]
            }
        except ValueError:
            # This can happen if there are incorrect dates in a document (e.g. April 31st)
            print "Could not parse date:"
            print text[max(0, match.start()-100):match.start()]
            print '>', text[match.start():match.end()], '<'
            print datetime_args
            print text[match.end():match.end()+100]
