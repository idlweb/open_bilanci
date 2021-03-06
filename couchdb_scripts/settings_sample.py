# Google Account credentials (Oauth2)
oauth2_key_path='PATH/TO/JSONFILE.JSON'

# gdoc keys
gdoc_keys= {
    'titoli':
        'INSERT_DOCUMENT_KEY_HERE',
    'voci':
        'INSERT_DOCUMENT_KEY_HERE',
    'simplify':
        'INSERT_DOCUMENT_KEY_HERE',
}


accepted_types={
    'titoli':{
        'csv_keys':["tipo","quadro", "titolo"]
    },
    'voci':{
        'csv_keys':["tipo","quadro","titolo", "voce"],
    },
    'simplify':{
        'csv_keys':["tipo","quadro", "titolo","voce"]
    }
}


accepted_servers = {
    'localhost': {
        'host': 'localhost',
        'port': '5984',
        'user': '',
        'password':'',
        'raw_db_name':'DB_NAME_HERE',
        'normalized_titoli_db_name':'DB_NAME_HERE',
        'normalized_voci_db_name': 'DB_NAME_HERE',
    },
    'staging': {
        'host': 'staging.depp.it',
        'port': '5984',
        'user': 'USER',
        'password':'PASSW',
        'raw_db_name':'DB_NAME_HERE',
        'normalized_titoli_db_name':'DB_NAME_HERE',
        'normalized_voci_db_name': 'DB_NAME_HERE',
    },
}

