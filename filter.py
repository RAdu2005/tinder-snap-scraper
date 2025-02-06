import os
import glob

current_directory = os.getcwd()
txt_files = glob.glob(os.path.join(current_directory, "bios/*.txt"))
leads = []

for file in txt_files:
    print(f"Processing file: {file}")
    data = open(file, 'r', encoding='utf-8')

    lines = data.readlines()

    for line in lines:
        line = line.split(',')
        if ("found_snap:" in line[0]) and (line[0][12:] not in leads) and (line[0][12:] not in ['-1', 'None']):
            leads.append(line[0][12:])

for i in leads:
    print(i)