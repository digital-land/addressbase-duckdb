.PHONY: init all clean clobber prune server
.DELETE_ON_ERROR:

AddressBase_ZIP=cache/AB76GB_CSV.zip
AddressBase_HEADERS_CSV=cache/addressbase-premium-header-files.zip
Classification_ZIP=cache/addressbase-product-classification-scheme.zip
Classification_CSV=data/addressbase-classification.csv
Database_DIR=database
Database_STAMP=$(Database_DIR)/blpu.parquet
Database_FILE=$(Database_DIR)/addressbase.duckdb

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
