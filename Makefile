.PHONY: init all clean clobber prune server
.DELETE_ON_ERROR:

Database_DIR=database/
Database_FILE=$(Database_DIR)addressbase.duckdb

Classification_ZIP=cache/addressbase-product-classification-scheme.zip
Classification_CSV=database/addressbase-classification.csv

Custodian_CSV=cache/organisation.csv
Custodian_LOOKUP_CSV=database/addressbase-custodian.csv

AddressBase_ZIP=cache/AB76GB_CSV.zip
AddressBase_HEADERS_CSV=cache/addressbase-premium-header-files.zip
Database_STAMP=$(Database_DIR)blpu.parquet

all::	$(Classification_CSV) $(Custodian_LOOKUP_CSV) $(Database_FILE)

$(Classification_CSV):	$(Classification_ZIP) bin/classification.py
	@mkdir -p data
	python3 bin/classification.py

$(Custodian_CSV):
	curl -s -o $(Custodian_CSV) https://files.planning.data.gov.uk/organisation-collection/dataset/organisation.csv

$(Custodian_LOOKUP_CSV):	$(Custodian_CSV) bin/custodian.py
	python3 bin/custodian.py

$(Database_STAMP):	$(AddressBase_ZIP) $(AddressBase_HEADERS_CSV) bin/load.py
	python3 bin/load.py

$(Database_FILE):	$(Database_STAMP) $(Custodian_LOOKUP_CSV) bin/database.py
	python3 bin/database.py

init:
	pip3 install -r requirements.txt

server:	$(Database_FILE)
	python3 bin/server.py

clobber:
	rm -f $(DB) $(Classification_CSV) $(Custodian_LOOKUP_CSV)
	rm -rf $(Database_DIR)

clean:	clobber
	rm -rf ./var

prune:	clean
	rm -rf ./cache
