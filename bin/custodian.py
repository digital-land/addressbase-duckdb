#!/usr/bin/env python3

# extract the AddressBase Local Custodian Code -> organisation name lookup
# from the planning.data.gov.uk organisation dataset.

import csv

in_path = "./cache/organisation.csv"
out_path = "./database/addressbase-custodian.csv"

if __name__ == "__main__":
    with open(in_path, newline="") as f:
        pairs = sorted(
            {(row["addressbase-custodian"], row["name"]) for row in csv.DictReader(f) if row["addressbase-custodian"]}
        )
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["LOCAL_CUSTODIAN_CODE", "NAME"])
        writer.writerows(pairs)
