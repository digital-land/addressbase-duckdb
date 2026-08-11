.PHONY: init all clean clobber prune server
.DELETE_ON_ERROR:

Database_DIR=database/
Database_FILE=$(Database_DIR)addressbase.duckdb

Classification_ZIP=cache/addressbase-product-classification-scheme.zip
Classification_CSV=database/addressbase-classification.csv

AddressBase_ZIP=cache/AB76GB_CSV.zip
AddressBase_HEADERS_CSV=cache/addressbase-premium-header-files.zip
Database_STAMP=$(Database_DIR)blpu.parquet

all::	$(Classification_CSV) $(Database_FILE)

$(Classification_CSV):	$(Classification_ZIP) bin/classification.py
	@mkdir -p data
	python3 bin/classification.py

$(Database_STAMP):	$(AddressBase_ZIP) $(AddressBase_HEADERS_CSV) bin/load.py
	python3 bin/load.py

$(Database_FILE):	$(Database_STAMP) bin/database.py
	python3 bin/database.py

init:
	pip3 install -r requirements.txt

server:	$(Database_FILE)
	python3 bin/server.py

clobber:
	rm -f $(DB) $(Classification_CSV)
	rm -rf $(Database_DIR)

clean:	clobber
	rm -rf ./var

prune:	clean
	rm -rf ./cache
