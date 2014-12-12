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
            __table__.append(row)
    return __table__

def is_not_human_disease(disease):
    for row in get_table():
        if row['label'] == disease:
            return row['is_not_disease'] or row['not_human_disease']

__disease_to_parent__ = None
def get_disease_parents(disease):
    global __disease_to_parent__
    if not __disease_to_parent__:
        __disease_to_parent__ = {}
        for row in get_table():
            __disease_to_parent__[row['label']] = row['parent_label']
    parents = []
    parent = __disease_to_parent__.get(disease)
    if parent:
        parents.append(parent)
        while parents[-1] in __disease_to_parent__:
            parents.append(__disease_to_parent__[parents[-1]])
    return parents
