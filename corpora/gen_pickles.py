"""
Generate training and validation pickles with cleaned ariticle content
"""
# Load articles
import datetime
import iterate_resources
start = datetime.datetime.now()
resources = list(iterate_resources.iterate_resources("corpora/healthmap/train"))
validation_resources = list(iterate_resources.iterate_resources("corpora/healthmap/devtest"))
print "full train set size:", len(resources)
print "full validation set size:", len(validation_resources)
original_resource_subset = list(iterate_resources.pseudo_random_subset(resources, 1.0))
print "train subset size: ", len(original_resource_subset)
original_validation_subset = list(iterate_resources.pseudo_random_subset(validation_resources, 1.0))
print "validation subset size: ", len(original_validation_subset)
print "time:", datetime.datetime.now() - start

# Process articles
import process_resources
from process_resources import resource_url, process_resources, attach_translations, filter_exceptions, resource_url
start = datetime.datetime.now()
attach_translations(original_resource_subset + original_validation_subset)
resource_subset, train_exceptions = filter_exceptions(process_resources(original_resource_subset))
validation_subset, validation_exceptions = filter_exceptions(process_resources(original_validation_subset))
print "Training resources processed:", len(resource_subset),'/',len(original_resource_subset)
print "Validation resources processed:", len(validation_subset),'/',len(original_validation_subset)
print "time:", datetime.datetime.now() - start

# Create pickles
import pickle
with open('training.p', 'wb') as f:
    pickle.dump(resource_subset, f)
with open('validation.p', 'wb') as f:
    pickle.dump(validation_subset, f)
