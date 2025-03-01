# MUCSMake 
# Utility to collect student lab submissions

import getpass
import sys
import toml
import os 
import re
import shutil
from datetime import datetime

import tomlkit



from tomlkit import document, table, comment, dumps, loads
from csv import DictReader, DictWriter
from subprocess import PIPE, run, STDOUT, Popen, TimeoutExpired, CalledProcessError


class Config:
    def __init__(self,class_code, run_valgrind, base_path, lab_window_path, lab_submission_directory, test_files_directory, roster_directory):
        self.class_code = class_code
        self.run_valgrind = run_valgrind
        self.base_path = base_path
        self.lab_window_path = base_path + class_code + lab_window_path
        self.lab_submission_directory = base_path + class_code + lab_submission_directory
        self.roster_directory = base_path + class_code + roster_directory
        self.test_files_directory = base_path + class_code + test_files_directory



CONFIG_FILE = "config.toml"
date_format = "%Y-%m-%d_%H:%M:%S"


def main(username, class_code, lab_name, file_name):
    # Stage 1 - Prepare Configuration
    colorama_init()
    if not os.path.exists(CONFIG_FILE):
        print(f"{CONFIG_FILE} does not exist, creating a default one")
        prepare_toml_doc()
        print("You'll want to edit this with your correct information. Cancelling further program execution!")
        exit()
    config_obj = prepare_config_obj()
    # Stage 2 - Prepare Compilation
    lab_window_file_status = verify_lab_window(config_obj, lab_name)
    if not lab_window_file_status:
        print("*** Lab number missing or invalid. Please check again. ***")
    lab_file_status = verify_lab_file_existence(config_obj, file_name)
    if not lab_file_status:
        print(f"*** Error: file {file_name} does not exist in the current directory. ***")
        exit()
    lab_header_inclusion = verify_lab_header_inclusion(config_obj, file_name, lab_name)
    if not lab_header_inclusion:
        print(f"*** Warning: your submission {file_name} does not include the lab header file. ***")
    grader = determine_section(config_obj, username)
    student_temp_dir = prepare_test_directory(config_obj, file_name, lab_name, username)
    # Stage 3 - Compile and Run
    compile_and_run_submission(config_obj, student_temp_dir)




# Uses a Regex string to detect if the lab header has been included in the file
def verify_lab_header_inclusion(config_obj, file_name, lab_name):
    search_pattern = f"^(#include)\s*(\"{lab_name}.h\")"
    with open(file_name, 'r') as c_file:
        for line in c_file:
            if re.search(search_pattern, line):
                return True
    return False
def verify_lab_file_existence(config_obj, file_name):
    if os.path.exists(file_name):
        return True
    return False
def retrieve_lab_window(config_obj, lab_nsame):
    with open(config_obj.lab_window_path, 'r', newline="") as window_list:
        next(window_list)
        fieldnames = ["lab_name", "start_date", "end_date"]
        csvreader = DictReader(window_list, fieldnames=fieldnames)
        for row in csvreader:
            if row['lab_name'] == lab_name:
                today = datetime.today()
                start_date = datetime.strptime(row['start_date'], date_format)
                end_date = datetime.strptime(row['end_date'], date_format)
                if start_date < today < end_date:
                    return True
                else:
                    print("Submission outside of window")
                    return False
        print("Unable to find lab name")

    return False
def verify_lab_window(config_obj, lab_name):
    with open(config_obj.lab_window_path, 'r', newline="") as window_list:
        next(window_list)
        fieldnames = ["lab_name", "start_date", "end_date"]
        csvreader = DictReader(window_list, fieldnames=fieldnames)
        for row in csvreader:
            if row['lab_name'] == lab_name:
                return True
    return False
def determine_section(config_obj, username):
    # to-do: can we parallelize this search?
    # probably just use a grep subprocess
    for roster_filename in os.listdir(config_obj.roster_directory):
        with open(config_obj.roster_directory + "/" + roster_filename, 'r') as csv_file:
            next(csv_file)
            fieldnames = ['pawprint', 'canvas_id', 'name', 'date']
            csv_roster = DictReader(csv_file, fieldnames=fieldnames)
            for row in csv_roster:
                if username == row['pawprint']:
                    return roster_filename.replace(".csv", '')

def prepare_test_directory(config_obj, file_name, lab_name, username):
    lab_files_dir = config_obj.test_files_directory + "/" + lab_name + "_temp"
    student_temp_files_dir = lab_files_dir + "/" + lab_name + "_" + username + "_temp"
    print(student_temp_files_dir)
    os.makedirs(student_temp_files_dir)
    for entry in os.scandir(lab_files_dir):
        if entry.is_dir():
            continue
        shutil.copy(entry.path, student_temp_files_dir)
    shutil.copy(file_name, student_temp_files_dir)
    return student_temp_files_dir

def compile_and_run_submission(config_obj, temp_dir):
    is_make = False
    for entry in os.scandir(temp_dir):
        print(entry)
        if (entry.name == "Makefile"):
            is_make = True
            break
    result = None
    if (is_make):
        result = run(["make"], cwd=temp_dir)
    else:
        result = run(["compile"], cwd=temp_dir)
    # returns 2 if doesnt link
    if (result.returncode):
        return 1
    executable_path = temp_dir + "/a.out"
    stdout = run([executable_path], timeout=5, stdout=PIPE, stderr=PIPE, universal_newlines=True).stdout
    stderr = run(["valgrind", executable_path], stdout=PIPE, stderr=PIPE, universal_newlines=True).stderr

    print(stdout)
    if re.search("[1-9]\d*\s+errors", stderr):
        print("Detected valgrind errors")
    if not re.search("(All heap blocks were freed -- no leaks are possible)", stderr):
        print("Memory leak detected")


# Creates a new toml file.
def prepare_toml_doc():
    doc = document()

    general = table()
    general.add("class_code", "2050")
    general.add(comment("Checks for a C header file corresponding to the lab name in the submission."))
    general.add("check_lab_header", True)
    general.add("run_valgrind", True)
    
    paths = table()
    paths.add("base_path", "/cluster/pixstor/class/")
    paths.add("lab_window_path", "")
    paths.add("lab_submission_directory", "/submissions")
    paths.add("test_files_directory", "/test_files")
    paths.add("roster_directory", "/csv_rosters")
    doc['general'] = general
    doc['paths'] = paths


    with open(CONFIG_FILE, 'w') as f:
        f.write(dumps(doc))
    print(f"Created default {CONFIG_FILE}")
    
def prepare_config_obj():
    with open(CONFIG_FILE, 'r') as f:
        content = f.read()
    doc = tomlkit.parse(content)

    # Extract values from the TOML document
    general = doc.get('general', {})
    paths = doc.get('paths', {})
    canvas = doc.get('canvas', {})


    return Config(class_code = general.get('class_code'), run_valgrind = general.get('run_valgrind'), 
    base_path = paths.get('base_path'), lab_submission_directory = paths.get('lab_submission_directory'), test_files_directory = paths.get('test_files_directory'),
    roster_directory = paths.get('roster_directory'), lab_window_path = paths.get('lab_window_path'))


if __name__ == "__main__":
    # Stage 0 - Collect Command Args
    # username = getpass.getuser()
    username = 'adnnk2'
    class_code = sys.argv[1]
    lab_name = sys.argv[2]
    file_name = sys.argv[3]
    main(username, class_code, lab_name, file_name)



