import argparse
import json, yaml
import os
import re
import random
import urllib2
import concurrent
import concurrent.futures

def process_resource_file(file_path):
    with open(file_path) as resource:
        header = None
        content = None
        #Parse the file into the header and content sections
        for line in resource:
            if header is None:
                if not line.startswith('---\n'):
                    raise Exception('Cannot parse resource.')
                header = ''
            elif content is None:
                if line.startswith('---\n'):
                    content = ''
                else:
                    header += line
            else:
                content += line
        if content is None:
            print 'Cannot parse resource: ', file_path
            print 'Missing second ---'
            print header
            return None
        resource_obj = yaml.load(header)
        resource_obj['content'] = content
        return resource_obj

def process_resource_files(file_paths):
    return [process_resource_file(f) for f in file_paths]

def iterate_resources(path, n_jobs=0):
    for root, dirs, files in os.walk(path):
        file_paths = (os.path.join(root, file_name) for file_name in files)
        if n_jobs != 1:
            with concurrent.futures.ProcessPoolExecutor(None if n_jobs <= 0 else n_jobs) as executor:
                # executor.map is not lazy so this will be slower when iterating subsets
                for resource in executor.map(process_resource_file, file_paths):
                    yield resource
        else:
            for file_path in file_paths:
                yield process_resource_file(file_path)


def pseudo_random_subset(resources, portion):
    """
    Uses the resource id to deterministically choose whether
    to include it in a pseudorandom subset.
    Because the ids are also used to determine the category
    to avoid bias we take their random hash modulo .1
    as only the first decimal is used to determine the data set.
    """
    for resource in resources:
        #The hashes that the RNG seed function creates are platform dependent
        #so 64 bit systems return different random values.
        #However, we can get 32 bit system hashes on 64 bit systems by bitmasking the hash.
        resource_id_hash = hash(resource.get('_id')) & 0xffffffff
        #If we were just trying to match the behavior of python's built-in hash function we
        #would need to covert to a signed int, but because the RNG hashes strings to
        #unsigned longs don't need to do this:
        #http://stackoverflow.com/questions/23260975/how-does-python-2-7-3-hash-strings-used-to-seed-random-number-generators
        random_value = random.Random(resource_id_hash).random()
        if 10 * (random_value % .1) < portion:
            yield resource

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-path', default='healthmap')
    args = parser.parse_args()

    import datetime
    start = datetime.datetime.now()
    
    count = 0
    unscrapable_count = 0
    url_counts = {}
    for resource in iterate_resources(args.path):
        if random.random() < 0.01:
            print count, "resource files iterated over so far..."
        count += 1
        source_metadata = resource['sourceMeta']
        if source_metadata.get('unscrapable'): unscrapable_count += 1
        source_url = source_metadata.get('sourceUrl')
        url_counts[source_url] = url_counts.get(source_url, 0) + 1
    
    print "Total resources iterated: ", count
    print "Unscrapable resources: ", unscrapable_count
    print "Time: ", datetime.datetime.now() - start
    print "Duplicate urls:"
    for url, count in sorted(url_counts.items(), key=lambda a: a[1], reverse=True)[0:10]:
        if count > 1:
            print count, url
    print "Unique urls:"
    print len([url for url, count in url_counts.items() if count == 1])
    print "Host counts:"
    host_counts = {}
    for url, count in url_counts.items():
        parsed_url = urllib2.urlparse.urlparse(url)
        host_counts[parsed_url.hostname] = host_counts.get(parsed_url.hostname, 0) + count
    for host, count in sorted(host_counts.items(), key=lambda a: a[1], reverse=True)[0:10]:
        print count, host
