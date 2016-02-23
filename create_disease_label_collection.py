import pymongo
import disease_label_table
import config

if __name__ == '__main__':
    db = pymongo.Connection(config.mongo_url)['girder']
    db.drop_collection('diseaseNames')
    for label in disease_label_table.get_labels():
        db['diseaseNames'].insert({'_id': label})
