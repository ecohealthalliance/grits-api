# coding=utf8
import json
import yaml
import base64, urllib2, urllib
import argparse
import random
import scrape
import concurrent
import concurrent.futures
import datetime
import os, sys

def create_resource_file(location, header_data, content):
    """
    Create a file corresponding to the resource with a YML header that can be
    inspected on github.
    """
    directory = os.path.dirname(location)
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(location, 'w+') as file:
        file.write('---\n')
        try:
            yaml_string = yaml.safe_dump(header_data)
        except yaml.representer.RepresenterError:
            for k,v in header_data['sourceMeta'].items():
                if isinstance(v, unicode):
                    if '\r' in v:
                        header_data['sourceMeta'][k] = v.replace('\r', '').encode('utf8')
                    else:
                        header_data['sourceMeta'][k] = v.encode('utf8')
            yaml_string = yaml.safe_dump(header_data)
        file.write(yaml_string)
        file.write('---\n')
        if content:
            file.write(content.encode('utf8'))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-username')
    parser.add_argument('-password')
    parser.add_argument('-server', default='https://grits.ecohealth.io:443/')
    parser.add_argument('-folderId', default='532c66cdf99fe75cf53758f7')
    parser.add_argument('-out', default='healthmap')
    parser.add_argument('-state_file', default=None)
    parser.add_argument('-offset', default=None)
    parser.add_argument('-limit', default=300)
    parser.add_argument('-verbose', default=False)
    args = parser.parse_args()
    
    if not args.state_file:
        print """
        Specify a state_file to keep track of how much of the corpus has been fetched.
        """
    
    print "Authenticating with %s ..." % args.server
    req = urllib2.Request(args.server + "gritsdb/api/v1/user/authentication")
    req.add_header('Authorization',
        'Basic ' + base64.urlsafe_b64encode(args.username+':'+args.password)
    )
    auth_token = json.loads(urllib2.urlopen(req).read()).get("authToken")
    print "Processing resources from %s ..." % args.server

    print """
    Keyboard interrupts will not take immediate effect because of the
    way python's furtures work. You may need to wait a minute while all the
    threads stop.
    """
    if args.offset and args.state_file:
        raise Exception("An offset cannot be specified when a state file is used.")
    initial_offset = int(args.offset) if args.offset else 0
    url_counts = {}
    if args.state_file:
        if not os.path.exists(args.state_file):
            print """
            Warning: %s does not exist. It will be created.
            """ % args.state_file
        else:
            with open(args.state_file) as f:
                state = json.load(f)
                url_counts = state['url_counts']
                initial_offset = state['offset']
    resource_count = 35462
    def make_resource_generator(offset, original_limit):
        start_time = datetime.datetime.now()
        while offset < resource_count:
            limit = min(resource_count, original_limit + offset) - offset
            if args.state_file:
                with open(args.state_file, 'w+') as f:
                    json.dump({
                        'offset' : offset,
                        'url_counts' : url_counts,
                    }, f)
            print ''
            print "At resource number ", offset, " of ", resource_count
            print 100 * offset / resource_count, '% complete!'
            print "Time elapsed: ", datetime.datetime.now() - start_time
            print ''
            req = urllib2.Request(args.server + "gritsdb/api/v1/item?" + urllib.urlencode({
                'folderId' : args.folderId,
                'limit' : limit,
                'offset' : offset,
                # Sort the collection by creation date so offsets stay consistent
                'sort' : 'created'
            }))
            offset += limit
            req.add_header('Cookie', 'authToken=' + json.dumps(json.dumps(auth_token)))
            open_req = urllib2.urlopen(req)
            resources = json.loads(open_req.read())
            # I'm using Python's futures to speed up the scraping.
            # On a AWS small instance I'm getting around 100 sites scraped per minute,
            # whereas if I only use 1 worker it's less than 50 per minute.
            # I think most of the speed up comes from switching threads when http requests
            # block. On a multicore machine using processes might work better than threads
            # since they wouldn't be competing for CPU time.
            # The reason I used futures instead of a task queue like celery is
            # is to avoid external dependencies (e.g. setting up a message broker and running a daemon).
            # However, I'm finding futures to be kind of tricky to deal with.
            # Keyboard interrupts are broken, (they eventually work but you have to wait a few minutes).
            # I think that exceptions in workers won't stop the process right away
            # because they don't get thrown in the main thead until the result of the worker
            # thread is accessed.
            # Also, I'm a bit worried that some of the scraping code could
            # do something that isn't thread safe, but any non-deterministic
            # effects should should show up when we diff re-fetched versions of the corpus.
            import concurrent.futures, sys
            with concurrent.futures.ThreadPoolExecutor(max_workers=11) as executor:
                
                future_to_data = {}
                for grits_data in resources:
                    source_link = grits_data.get('meta', {}).get('link')
                    if source_link in url_counts:
                        if args.verbose: print "Duplicate URL found: ", source_link
                        # This doesn't exclude sites with unique google news urls
                        # that redirect to the same site.
                        yield grits_data, {
                            'sourceUrl' : source_link,
                            'unscrapable' : True,
                            'exception' : "duplicate",
                        }
                        url_counts[source_link] += 1
                        continue
                    else:
                        url_counts[source_link] = 1
                    current_future = executor.submit(scrape.scrape, source_link)
                    future_to_data[current_future] = grits_data
                    remaining_futures = future_to_data.copy()
                future_iterator = concurrent.futures.as_completed(future_to_data, timeout=300)
                while True:
                    try:
                        future = future_iterator.next()
                        source_data = future.result()
                        grits_data = remaining_futures.pop(future)
                        yield grits_data, source_data
                    except StopIteration:
                        break
                    except GeneratorExit:
                        Exception("Exception somewhere in the code using this generator.")
                    except concurrent.futures._base.TimeoutError as e:
                        print "Remaining futures:"
                        print remaining_futures
                        raise Exception("Time leak caused by unknown resource.")
                        
    scraped_resource_generator = make_resource_generator(initial_offset, int(args.limit))
    for header_data, source_data in scraped_resource_generator:
        source_metadata_props = [
            'promedId'     ,
            'title'        ,
            'linkedReports',
            'zoomLat'      ,
            'zoomLon'      ,
            'zoomLevel'    ,
            'unscrapable'  ,
            'sourceUrl'    ,
            'exception'
        ]
        header_data['sourceMeta'] = { key : source_data[key] for key in source_metadata_props if key in source_data }
        content = source_data.get('content')
        # Using 60/20/20 training/validation/test set split.
        # There are lots of ways to do it, further discussion here:
        # http://stackoverflow.com/questions/13610074/is-there-a-rule-of-thumb-for-how-to-divide-a-dataset-into-training-and-validatio
        
        # Use the id to seed a pseuorandom number generator for reproducability
        # no matter what the offset or sort order is.
        # However, Python's random module doesn't hash strings the same way
        # across platforms,
        # so I do the hashing manually for backwards compatibility.
        # The bitmask is used to make 64bit platform hashes match those of 32bit platforms.
        # If we were just trying to match the behavior of Python's built-in hash function
        # we would need to covert to a signed int, but because the RNG hashes strings to
        # unsigned longs we don't need to do this:
        # http://stackoverflow.com/questions/23260975/how-does-python-2-7-3-hash-strings-used-to-seed-random-number-generators
        id_hash = hash(header_data['_id']) & 0xffffffff
        r = random.Random(id_hash).random()
        directory = None
        if r < 0.6:
            directory = os.path.join(args.out, 'train/')
        elif r < 0.8:
            directory = os.path.join(args.out, 'devtest/')
        else:
            directory = os.path.join(args.out, 'test/')
        create_resource_file(directory + header_data['_id'] + '.md', header_data, content)
    print "done"