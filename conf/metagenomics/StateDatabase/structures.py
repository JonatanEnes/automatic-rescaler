# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils
from conf.metagenomics.StateDatabase.structures.application.multiple_services import \
    add_multiple_services_as_applications
from conf.metagenomics.StateDatabase.structures.containers import add_containers
from conf.metagenomics.StateDatabase.structures.hosts import add_hosts

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "structures"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)
    add_containers(handler)
    add_hosts(handler)
    #add_single_application(handler)
    add_multiple_services_as_applications(handler)