def extract_features(resources):
    import json
    with open("keywords.json") as f:
        keywords = json.load(f)

    def create_tag_objects(tags, metadata):
        for tag in tags:
            my_metadata = metadata.copy()
            my_metadata['tag'] = tag
            yield my_metadata

    def take_range(start, end, iterator):
        for i in range(start):
            iterator.next()
        for i in range(end - start):
            yield iterator.next()

    all_tags = []
    all_tags += create_tag_objects(keywords['hosts'], { 'category' : 'hosts' })
    all_tags += create_tag_objects(keywords['pathogens'], { 'category' : 'pathogens' })
    all_tags += create_tag_objects(keywords['symptoms'], { 'category' : 'symptoms' })
    all_tags += create_tag_objects(keywords['diseases'], { 'category' : 'diseases' })

    from pattern.en import parsetree

    def normalize_tag(tag):
        return ' '.join([w.string.lower() for w in parsetree(tag).words])

    import re
    tag_re = re.compile('\\b(' + '|'.join([t['tag'] for t in all_tags]) + ')\\b', re.I)
    tag_set = set([t['tag'] for t in all_tags])

    def find_tags_re(resources):
        for idx, resource in enumerate(resources):
            content = resource['cleanContent']
            yield list(tag_re.finditer(resource['cleanContent'])), resource

    def get_tags(matches, resource):
        for match in matches:
            yield resource['cleanContent'][match.start():match.end()].lower()

    for matches, resource in find_tags_re(resources):
        feature_dict = {}
        #TODO: Measure accuracy difference of just using booleans
        #to measure keyword presence rather than counts
        for rawtag in get_tags(matches, resource):
            tag = normalize_tag(rawtag)
            feature_dict[tag] = feature_dict.get(tag, 0) + 1
        yield feature_dict
