import csv
import os

__table__ = None

# To update the csv from our google sheet use:
# wget --no-check-certificate --output-document=disease_label_table.csv 'https://docs.google.com/spreadsheet/ccc?key=1MvkBBsvGP6Ax_bPfQJupjRiPDN803IpG1vB-iFzsr6M&output=csv'
def get_table():
    global __table__
    if __table__:
        return __table__
    __table__ = []
    curdir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(curdir, "disease_label_table.csv")) as f:
        header = csv.reader(f, delimiter=',', quoting=csv.QUOTE_NONE).next()
        reader = csv.DictReader(f,
            fieldnames=header,
            delimiter=',',
            quoting=csv.QUOTE_NONE)
        for row in reader:
            for key, value in row.items():
                if value == "TRUE":
                    row[key] = True
                elif value == "FALSE":
                    row[key] = False
                if value == "":
                    del row[key]
            __table__.append(row)
    return __table__

def is_not_human_disease(disease):
    for row in get_table():
        if row['label'] == disease:
            return row.get('is_not_disease') or row.get('not_human_disease')

__disease_to_parents__ = None
def get_inferred_labels(disease):
    global __disease_to_parents__
    if not __disease_to_parents__:
        __disease_to_parents__ = {}
        for row in get_table():
            if 'parent_label' in row:
                __disease_to_parents__[row['label']] = [row['parent_label']]
    inferred_labels = []
    parents = __disease_to_parents__.get(disease, [])
    unresolved_labels = list(parents)
    while len(unresolved_labels) > 0:
        label = unresolved_labels.pop()
        if label in inferred_labels: continue
        inferred_labels.append(label)
        new_parents = list(__disease_to_parents__.get(label, []))
        unresolved_labels += new_parents
    return inferred_labels
