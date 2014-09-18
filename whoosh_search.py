import requests, urlparse, json
import os.path
import whoosh.fields, whoosh.query, whoosh.index
import wikipedia, urllib2

schema = whoosh.fields.Schema(
    label=whoosh.fields.TEXT(stored=True),
    content=whoosh.fields.TEXT(stored=True),
    url=whoosh.fields.ID(stored=True)
)

def download_google_sheet(key, default_type=None):
    request = requests.get(
        'https://spreadsheets.google.com/feeds/list/' + key +
        '/od6/public/values?alt=json-in-script&callback=jsonp'
    )
    spreadsheet_data = json.loads(
        request.text[request.text.find('jsonp(') + 6:-2]
    )
    result = []
    for entry in spreadsheet_data['feed']['entry']:
        result.append({
            colname.split('gsx$')[1] : val.get('$t')
            for colname, val in entry.items()
            if colname.startswith('gsx$')
        })
    return result

def build_index():
    label_links = download_google_sheet('17O_ZrOJxCBAedAuJJFdqKuR63DMrsGPJvqREU_E3mY8')
    print "downloading", len(label_links), "articles"
    
    for row in label_links:
        if row['wikilink'].startswith('http://en.wikipedia.org/wiki/'):
            page_name = row['wikilink'].split('http://en.wikipedia.org/wiki/')[1]
            print page_name
            row['content'] = wikipedia.page(page_name).content
    
    if not os.path.exists("wiki_index"):
        os.mkdir("wiki_index")
    whoosh.index.create_in("wiki_index", schema)
    ix = whoosh.index.open_dir("wiki_index")
    writer = ix.writer()
    
    for row in label_links:
        if 'content' in row:
            writer.add_document(
                label=row['diseasename'],
                content=row['content'],
                url=row['wikilink']
            )
    writer.commit()

def search(text):
    #TODO: Use cosine similarity because it is bounded and possibly more effective.
    ix = whoosh.index.open_dir("wiki_index")
    terms = set(schema['content'].process_text(text))
    myquery = whoosh.query.Or([
        whoosh.query.Term('content', term) for term in terms
    ])
    with ix.searcher() as searcher:
        return [
            (r['label'], r.score)
            for r in searcher.search(myquery)
        ]

if __name__ == "__main__":
    print "building index..."
    build_index()
    print "test search..."
    for r in search('test'):
        print r
