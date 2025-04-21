# MUCSMakePy 
# Utility to collect student lab submissions
# Written by Matt Marlow
# Based on Daphne Zou's original mucsmake script
# Spring 2025

import getpass
import sys
import os 
import re
import shutil
import signal
import stat
from datetime import datetime
from pathlib import Path
import tomlkit

# https://pypi.org/project/colorama/
from colorama import init as colorama_init
from colorama import Fore, Back
from colorama import Style


from tomlkit import document, table, comment, dumps
from csv import DictReader
from subprocess import DEVNULL, PIPE, run


class Config:
    def __init__(self,class_code: str, run_valgrind: str, base_path: str, 
    lab_window_path: str, lab_submission_directory: str, 
    test_files_directory: str, roster_directory: str,
    valid_dir: str, invalid_dir: str):
        self.class_code = class_code
        self.run_valgrind = run_valgrind
        self.base_path = base_path
        self.lab_window_path = base_path + class_code + lab_window_path
        self.lab_submission_directory = base_path + class_code + lab_submission_directory
        self.roster_directory = base_path + class_code + roster_directory
        self.test_files_directory = base_path + class_code + test_files_directory
        self.valid_dir = valid_dir
        self.invalid_dir = invalid_dir



    def get_base_path_with_class_code(self):
        return self.base_path + self.class_code




CONFIG_FILE = "config.toml"
date_format = "%Y-%m-%d_%H:%M:%S"


def main(username: str, class_code: str, lab_name: str, file_name: str):
    # Stage 1 - Prepare Configuration
    if not os.path.exists(path=CONFIG_FILE):
        print()
        prepare_toml_doc()
        handle_critical_error(f"{CONFIG_FILE} does not exist, creating a default one", "main")
        exit()
    config_obj:Config= prepare_config_obj()
    # Stage 2 - Verify Parameters and Submission
    lab_name_status = verify_lab_name(config_obj, lab_name)
    if not lab_name_status:
        print(f"{Fore.RED}*** Error: Lab number missing or invalid. Please check again. ***{Style.RESET_ALL}")
        exit()
    lab_file_status = verify_lab_file_existence(file_name)
    if not lab_file_status:
        print(f"{Fore.RED}*** Error: file {Style.RESET_ALL}{Fore.BLUE}{file_name}{Style.RESET_ALL}{Fore.RED} does not exist in the current directory. ***{Style.RESET_ALL}")
        exit()
    lab_header_inclusion = verify_lab_header_inclusion(file_name, lab_name)
    if not lab_header_inclusion:
        print(f"{Fore.YELLOW}*** Warning: your submission {Style.RESET_ALL}{Fore.BLUE}{file_name}{Style.RESET_ALL}{Fore.YELLOW} does not include the lab header file. ***{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}*** There's a good chance your program won't compile! ***{Style.RESET_ALL}")
    lab_window_status = verify_lab_window(config_obj, lab_name)
    if not lab_window_status:
        print(f"{Fore.YELLOW}*** Warning: your submission {Style.RESET_ALL}{Fore.BLUE}{file_name}{Style.RESET_ALL}{Fore.YELLOW} is outside of the submission window. ***{Style.RESET_ALL}")
    enrollment_status = verify_student_enrollment(config_obj)
    if not enrollment_status:
        print(f"{Fore.RED}*** Error: You are not enrolled in {Style.RESET_ALL}{Fore.BLUE}{config_obj.class_code}{Style.RESET_ALL}{Fore.RED} ")
    grader = determine_section(config_obj, username)
    
    student_temp_dir = prepare_test_directory(config_obj, file_name, lab_name, username)
    # Stage 3 - Compile and Run
    run_result = compile_and_run_submission(config_obj, student_temp_dir)
    clean_up_test_directory(student_temp_dir)
    # Stage 4 - Place Submission
    place_submission(config_obj, lab_window_status, run_result, grader, lab_name, file_name, username)
    # Stage 5 - Display Results
    display_results(config_obj, lab_window_status, run_result, grader, lab_name, file_name, username)



def place_submission(config_obj: Config, lab_window_status: bool, run_result: bool, grader: str, lab_name: str, file_name: str, username: str):
    submission_path = config_obj.lab_submission_directory + "/" + lab_name + "/" + grader
    directory_name = username + "_" + str(datetime.today()).replace(" ", "_")
    valid_path = submission_path + "/" + config_obj.valid_dir
    invalid_path = submission_path + "/" + config_obj.invalid_dir

    is_valid = lab_window_status and run_result
    if not os.path.exists(valid_path):
        os.makedirs(valid_path)
    if not os.path.exists(invalid_path):
        os.makedirs(invalid_path)




    if (is_valid):
        valid_student_dir = valid_path + "/" + directory_name
        os.makedirs(valid_student_dir)
        # sets directory to setgroupid, read/execute for users, and nothing else for non groups
        os.chmod(valid_student_dir, 0o2770)
        shutil.copy(file_name, valid_student_dir)
        file_name_specific = Path(file_name).name
        os.chmod(valid_student_dir + "/" + file_name_specific, stat.S_IRUSR | stat.S_IRGRP | stat.S_IXGRP)
        symlink_dir = submission_path + "/" + username
        # if the link existed previously, let's undo it
        if os.path.islink(symlink_dir):
            os.unlink(symlink_dir)
        os.symlink(valid_student_dir, symlink_dir, target_is_directory = True)
    else:
        invalid_student_dir = invalid_path + "/" + directory_name
        os.makedirs(invalid_student_dir)
        shutil.copy(file_name, invalid_student_dir)
    
    
def display_results(config_obj: Config, lab_window_status: bool, run_result: bool, grader: str, lab_name: str, file_name: str, username: str):
    
    print(f"{Fore.BLUE}========================================={Style.RESET_ALL}")
    print(f"Course:     {config_obj.class_code}")
    print(f"Section/TA: {grader}")
    print(f"Assignment: {lab_name}")
    print(f"User:       {username}")
    print(f"Submission: {file_name}")
    print(f"{Fore.BLUE}========================================={Style.RESET_ALL}")
    print(f"{Fore.BLUE}***********SUBMISSION COMPLETE**********{Style.RESET_ALL}")
    print(f"\n")
    if (lab_window_status == False):
        print(f"{Fore.RED}========================================={Style.RESET_ALL}")
        print(f"{Fore.RED}*******OUTSIDE OF SUBMISSION WINDOW******{Style.RESET_ALL}")
        print(f"{Fore.RED}========================================={Style.RESET_ALL}")
    elif (run_result == False): 
        print(f"{Fore.RED}========================================={Style.RESET_ALL}")
        print(f"{Fore.RED}************FAILED TO COMPILE************{Style.RESET_ALL}")
        print(f"{Fore.RED}========================================={Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}========================================={Style.RESET_ALL}")
        print(f"{Fore.GREEN}**********SUBMISSION SUCCESSFUL**********{Style.RESET_ALL}")
        print(f"{Fore.GREEN}========================================={Style.RESET_ALL}")



# If a function encounters an error beyond user error (config mishap, course-side misconfiguration, etc) we need to stop 
# 
def handle_critical_error(message: str, calling_function: str):
    print(f"{Back.RED}*** CRITICAL ERROR IN {calling_function} *** {Style.RESET_ALL}")
    print(f"{Back.RED}{message} {Style.RESET_ALL}")
    print(f"{Back.RED}*** The configuration file is likely misconfigured. *** {Style.RESET_ALL}")
    print(f"{Back.RED}*** If you see this message during lab, contact your TA or professor immediately! ***{Style.RESET_ALL}")
    exit()
    

# Uses a Regex string to detect if the lab header has been included in the file
def verify_lab_header_inclusion(file_name: str, lab_name: str) -> bool:
    search_pattern = rf"^(#include)\s*(\"{lab_name}.h\")"
    with open(file_name, 'r') as c_file:
        for line in c_file:
            if re.search(search_pattern, line):
                return True
    return False
def verify_lab_file_existence(file_name: str) -> bool:
    if os.path.exists(file_name):
        return True
    return False
def verify_lab_window(config_obj: Config, lab_name: str) -> bool:
    with open(config_obj.lab_window_path, 'r', newline="") as window_list:
        _ = next(window_list)
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
                    return False
    return False
def verify_lab_name(config_obj: Config, lab_name: str) -> bool | None:
    try:
        with open(config_obj.lab_window_path, 'r', newline="") as window_list:
            _ = next(window_list)
            fieldnames = ["lab_name", "start_date", "end_date"]
            csvreader = DictReader(window_list, fieldnames=fieldnames)
            for row in csvreader:
                if row['lab_name'] == lab_name:
                    return True
            return False
    # handle misconfiguration of the config file
    # if this throws, the class code is probably wrong/not set
    except Exception as ex:
        handle_critical_error(str(ex), "verify_lab_name")
    
    
def verify_student_enrollment(config_obj: Config):
    path = os.environ.get("PATH", "")
    directories = path.split(":")
    target = config_obj.get_base_path_with_class_code() + "/bin"
    if target in directories:
        return True
    return False


def determine_section(config_obj: Config, username: str) -> str:
    for roster_filename in os.listdir(config_obj.roster_directory):
        with open(config_obj.roster_directory + "/" + roster_filename, 'r') as csv_file:
            _ = next(csv_file)
            fieldnames = ['pawprint', 'canvas_id', 'name', 'date']
            csv_roster = DictReader(csv_file, fieldnames=fieldnames)
            for row in csv_roster:
                if username == row['pawprint']:
                    return roster_filename.replace(".csv", '')
    # if we made it out of the loop... panic!
    # likely a misconfiguration of the grading roster
    handle_critical_error("No grader found", "determine_section")
    return ""

def prepare_test_directory(config_obj: Config, file_name: str, lab_name: str, username: str) -> str:
    lab_files_dir = config_obj.test_files_directory + "/" + lab_name + "_temp"
    student_temp_files_dir = lab_files_dir + "/" + lab_name + "_" + username + "_temp"
    os.makedirs(student_temp_files_dir)
    for entry in os.scandir(lab_files_dir):
        if entry.is_dir():
            continue
        shutil.copy(entry.path, student_temp_files_dir)
    shutil.copy(file_name, student_temp_files_dir)
    return student_temp_files_dir
def compile_and_run_submission(config_obj: Config, temp_dir: str) -> bool:
    is_make = False
    for entry in os.scandir(temp_dir):
        if (entry.name == "Makefile"):
            is_make = True
            break
    result = None
    if (is_make):
        result = run(["make"], cwd=temp_dir, stdout=DEVNULL, stderr=PIPE, universal_newlines=True)
    else:
        result = run(["compile"], cwd=temp_dir)
    # returns 2 if doesnt link
    if (result.returncode != 0):
        print(result.stderr)
        print(f"{Back.RED}*** Error: Submitted program does not compile! ***{Style.RESET_ALL}")
        return False
    executable_path = temp_dir + "/a.out"
    result = run(["stdbuf", "-oL", executable_path], timeout=5, stdout=PIPE, stderr=PIPE, universal_newlines=True)
    print(result.stdout)
    # we got an error
    if (result.returncode < 0):
        signum = -result.returncode
        if (signum == signal.SIGSEGV):
            print(f"{Fore.RED}Segmentation fault detected!{Style.RESET_ALL}")
    if (config_obj.run_valgrind):
        stderr = run(["valgrind", executable_path], stdout=PIPE, stderr=PIPE, universal_newlines=True).stderr
        if re.search(r"[1-9]\d*\s+errors", stderr):
            print(f"{Fore.RED}Valgrind: There were errors in your program!{Style.RESET_ALL}")
        if not re.search("(All heap blocks were freed -- no leaks are possible)", stderr):
            print(f"{Fore.RED}Valgrind: Memory leak detected!{Style.RESET_ALL}")
    return True
def clean_up_test_directory(temp_dir: str):
    shutil.rmtree(temp_dir)



# Creates a new toml file.
def prepare_toml_doc():
    doc = document()

    general = table()
    _ = general.add("class_code", "")
    _ = general.add(comment("Checks for a C header file corresponding to the lab name in the submission."))
    _ = general.add("check_lab_header", True)
    _ = general.add("run_valgrind", True)
    
    paths = table()
    _ = paths.add("base_path", "/cluster/pixstor/class/")
    _ = paths.add("lab_window_path", "")
    _ = paths.add("lab_submission_directory", "/submissions")
    _ = paths.add("test_files_directory", "/test_files")
    _ = paths.add("roster_directory", "/csv_rosters")
    _ = paths.add(comment("All valid submissions go here within your grader's submission folder."))
    _ = paths.add(comment("If it doesn't exist, it will be created."))
    _ = paths.add("valid_dir", ".valid")
    _ = paths.add(comment("All invalid submissions go here within your grader's submission folder."))
    _ = paths.add(comment("If it doesn't exist, it will be created."))
    _ = paths.add("invalid_dir", ".invalid")
    doc['general'] = general
    doc['paths'] = paths


    with open(CONFIG_FILE, 'w') as f:
        _ = f.write(dumps(doc))
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
    roster_directory = paths.get('roster_directory'), lab_window_path = paths.get('lab_window_path'), valid_dir = paths.get('valid_dir'), invalid_dir = paths.get('invalid_dir'))


if __name__ == "__main__":
    # Stage 0 - Collect Command Args
    username = getpass.getuser()
    colorama_init()
    if (len(sys.argv) < 4):
        print(f"{Fore.RED} *** Too few arguments provided! *** {Style.RESET_ALL}")
        print(f"{Fore.RED}Usage: mucsmake{Fore.BLUE} {{class_code}} {{lab_name}} {{file_to_submit}} {Style.RESET_ALL}")
        exit()
    class_code = sys.argv[1]
    lab_name = sys.argv[2]
    file_name = sys.argv[3]
    if (os.path.isdir(file_name)):
        # edge case to catch during preappended absolute paths
        print(f"{Fore.RED} *** Too few arguments provided! *** {Style.RESET_ALL}")
        print(f"{Fore.RED}Usage: mucsmake{Fore.BLUE} {{class_code}} {{lab_name}} {{file_to_submit}} {Style.RESET_ALL}")
        exit()
    main(username, class_code, lab_name, file_name)



