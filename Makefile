# Reproduce the whole project from nothing:   make all
# Rebuild from the raw file (keeps the download):   make fresh
PY ?= python

.PHONY: all data ingest profile clean analysis figures excel dashboard test fresh

all: ingest profile clean analysis figures excel dashboard test

data:        ; $(PY) src/00_download.py
ingest: data ; $(PY) src/01_ingest.py
profile:     ; $(PY) src/02_profile.py
clean:       ; $(PY) src/03_clean.py
analysis:    ; $(PY) src/04_analysis.py
figures:     ; $(PY) src/05_figures.py
excel:       ; $(PY) src/06_excel.py
dashboard:   ; $(PY) src/07_dashboard.py
test:        ; $(PY) -m pytest tests/ -q

fresh:       ; rm -f data/processed/retail.duckdb data/processed/raw_invoices.parquet && $(MAKE) all
