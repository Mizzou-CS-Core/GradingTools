# CS 1050 Backup Script 
# Matt Marlow 
import os 
import shutil
import sys
import re
import requests
import json
import toml

from subprocess import PIPE, run, STDOUT, Popen, TimeoutExpired
from csv import DictReader

canvas_api_prefix="https://umsystem.instructure.com/api/v1/"
cache_path = None
token = None
course_id = None
config_name = "config.toml"

timeout = 5

class Config: 
    def __init__(self, class_code, execution_timeout, local_storage_dir, hellbender_lab_dir, cache_dir, api_prefix, api_token, course_id, attendance_assignment_name_scheme):
        self.class_code = class_code
        self.execution_timeout = execution_timeout
        self.local_storage_dir = local_storage_dir
        self.hellbender_lab_dir = hellbender_lab_dir
        self.cache_dir = cache_dir
        self.api_prefix = api_prefix
        self.api_token = api_token
        self.course_id = course_id
        self.attendance_assignment_name_scheme = attendance_assignment_name_scheme





# help
def help():
    print("Usage: mucs_backup {lab_name} {TA name} {optional_args}")
    print("Optional arguments include: (in any order or combination)")
    print(" -x - Disables execution of compiled submissions")
    print(" -X - Disables compilation of copied submissions")
    print(" -n - Disables clearing labs if they already exist")
    print(" -m - Enables use of the makefile associated with a given lab")
    print(" -s - Prompts mucs_backup to accept a string to pass to stdin of the executed submission.")
    print("     An example of using -s: ")
    print("     mucs_backup lab2 Matt -s \"1 5 6\"")
    print(" 'a' - Prompts mucs_backup to query Canvas on if a student attended the in-person session.")
    print("     A course id and Canvas API token will need to be provided. ")
    print("     An example of using -a: ")
    print("     mucs_backup lab5 Matt -a 253049 1234556789abcdef")
    print("     Note that if you use -s in conjunction with -a, you will provide the string to stdin as the first argument prior to the course id and token. ")
    exit()
# Wrapper function for requests.get that prints for HTTP errors
def make_api_call(url, token, headers=None):
    response = None
    auth_header = {'Authorization': 'Bearer ' + token}
    try:
        if headers is None:
            response = requests.get(url, headers=auth_header) 
        else:
            response = requests.get(url, headers=headers + auth_header) 
        if (response.status_code == 200):
            return response
        elif (response.status_code == 401):
            print("Possibly a bad token")
        elif (response.status_code == 403):
            print("Forbidden")
        else:
            print("HTTP Error: " + str(response.status_code)) 
    
    except requests.exceptions.RequestException as e:
        print('Error:', e)
    return None
# Look up Mizzou pawprint from cached roster and convert to Canvas Student ID
def map_pawprint_to_user_id(pawprint):
    with open(cache_path + "/full_course_roster.json") as file:
        roster = json.load(file)
        for key in roster:
            if pawprint == key['login_id']:
                return key['id']
# Get individual submission of assignment from Canvas and determine if the score matches the criteria
def get_assignment_score(assignment_id, user_id, score_criteria):
        canvas_assignments_submission_api = canvas_api_prefix + "courses/" + str(course_id) + "/assignments/" + str(assignment_id) + "/submissions/" + str(user_id)
        response = make_api_call(canvas_assignments_submission_api, token)
        if response is not None:
            if (response.json()['entered_score'] >= score_criteria):
                return True
        return False
# Get list of students in course from Canvas and export to JSON file
def generate_course_roster(course_id, token, cache_path):
    # to do - optimize this to search by group instead 
        # probably not a ton faster since need to search by group then can get list of students by group
    course_api = canvas_api_prefix + "courses/" + course_id + "/users?per_page=400&include[]=test_student&page=" 
    # need to break it up into two pages since we hit the internal per page limit
    page_1 = make_api_call(course_api + "1", token)
    page_2 = make_api_call(course_api + "2", token)
    page_json = page_1.json()
    page_json += page_2.json()
    with open(cache_path + "/full_course_roster.json", 'w', encoding='utf-8') as file:
        json.dump(page_json, file, ensure_ascii=False, indent=4)

# Get list of assignments from Canvas and export to JSON file 
def generate_assignment_list(course_id, token, cache_path):
    canvas_assignments_api = canvas_api_prefix + "courses/" +course_id + "/assignments/"
    response = make_api_call(canvas_assignments_api, token)
    with open(cache_path + "/assignment_list.json", 'w', encoding='utf-8') as file:
        json.dump(response.json(), file, ensure_ascii=False, indent=4)

# Preamble function responsible for generating and prepping any necessary directories and files
def gen_directories(main_dir, cache_dir, lab_name, check_attendance, make_submission, clear_previous_labs, course_id=None, token=None):
    # "preamble" code - generates the local directories
    if not os.path.exists(main_dir):
        # create main lab dir
        os.makedirs(main_dir)
        print("Creating main lab dir")
    # if we're checking the attendance, then we need to prepare the cache
    if check_attendance == True:
        if course_id is None or token is None:
            print("Missing course ID or token for usage in checking attendance")
            exit()
        if os.path.exists(main_dir + "/" + cache_dir):
            print("A cache folder for the program already exists. Clearing it and rebuilding")
            shutil.rmtree(main_dir + "/" + cache_dir)
        os.makedirs(main_dir + "/" + cache_dir)
        generate_course_roster(course_id, token, cache_path = main_dir + "/" + cache_dir)
        generate_assignment_list(course_id, token, cache_path = main_dir + "/" + cache_dir)
   
    param_lab_dir = lab_name + "_backup"
    param_lab_path = main_dir + "/" + param_lab_dir
    # double check if the backup folder for the lab exists and if it does, just clear it out and regenerate
    # could also ask if the user is cool with this
    print("Checking path ", param_lab_path)
    if os.path.exists(param_lab_path) and clear_previous_labs:
        print("A backup folder for", lab_name, " already exists. Clearing it and rebuilding")
        shutil.rmtree(param_lab_path)
    print("Creating a backup folder for", lab_name)
    if make_submission:
        p = Popen(['cs1050start', lab_name], cwd=main_dir)
        p.wait()
    return param_lab_path

def perform_backup(main_dir, lab_name, param_lab_path, grader, compile_submission, execute_compilation, use_proc_input, check_attendance, make_submission, clear_previous_labs, proc_input = None):
    # locate the directories for submissions dependent on grader
    # also find the pawprints list for the grader
    grader_csv = hellbender_lab_directory + "/csv_rosters/" + grader + ".csv"
    submissions_dir = hellbender_lab_directory + "/submissions/" + lab_name + "/" + grader
    attendance_assignment_id = None
    # if attendance is true, then we need to go find the assignment we need
    if check_attendance == True:
        with open(cache_path + "/assignment_list.json", 'r') as file:
            assignment_json = json.load(file)
            assignment_name = "Attendance: Lab " + lab_name[3:]
            for key in assignment_json:
                if key['name'] == assignment_name:
                    attendance_assignment_id = key['id']
            if attendance_assignment_id == None:
                print("Failed to find attendance assignment for " + lab_name + ". Blocking further attendance checking.")
                check_attendance = False

    with open(grader_csv, "r", newline="") as pawprints_list:
        next(pawprints_list)
        fieldnames=["pawprint", "name"]
        csvreader = DictReader(pawprints_list, fieldnames=fieldnames)
        # for each name, we need to check if there's a valid submission
        for row in csvreader:
            # sanitize pawprint for best results
            pawprint = row['pawprint']
            pawprint = re.sub(r'\W+', '', pawprint)
            pawprint = pawprint.replace("\n", "")
            name = row['name']
            canvas_id = None
             
            if check_attendance == True:
                canvas_id = map_pawprint_to_user_id(pawprint)
                if not get_assignment_score(attendance_assignment_id, canvas_id, 1):
                    print(name + " was marked absent during the lab session and does not have a valid submission.")
                    continue
            pawprint_dir = submissions_dir + "/" + pawprint
            local_name_dir = param_lab_path + "/" + name
            if (clear_previous_labs == False):
                print(local_name_dir)
                if os.path.exists(local_name_dir) and not os.path.exists(local_name_dir + "/output.log"):
                    print("Student " + pawprint + " already has a non-empty log, skipping")
                    continue
                else:
                    print("Rebuilding student " + name + " directory")
                    shutil.rmtree(local_name_dir)
                
            if not os.path.exists(pawprint_dir):
                print("Student " + name + " does not have a valid submission. ")
                continue            
            # if there is a submission, copy it over to the local directory
            else:
                os.makedirs(local_name_dir)
                for filename in os.listdir(pawprint_dir):
                    shutil.copy(pawprint_dir + "/" + filename, local_name_dir)
                    if make_submission:
                        for lab_file in os.listdir(main_dir + "/" + lab_name):
                            if not os.path.exists(local_name_dir + "/" + lab_file) and not os.path.isdir(main_dir + "/" + lab_name + "/" + lab_file):
                                shutil.copy(main_dir + "/" + lab_name + "/" + lab_file, local_name_dir)
                    # if it's a c file, let's try to compile it and write the output to a file
                    if ".c" in filename and compile_submission:
                        if make_submission:
                            result = run(["make"], cwd = local_name_dir)
                        else:
                            compilable_lab = local_name_dir + "/" + filename
                            result = run(["gcc", "-Wall", "-Werror", "-o", local_name_dir + "/" + lab_name, compilable_lab])
                        if execute_compilation:
                            result = None
                            if make_submission:
                                try:
                                    result = run(["./" + local_name_dir+"/a.out"], timeout=timeout, stdout=PIPE, stderr=PIPE, universal_newlines=True, input=proc_input if use_proc_input else None)
                                    output = result.stdout
                                    log = open(local_name_dir + "/output.log", "w")
                                    log.write(output)
                                    log.close()
                                except TimeoutExpired:
                                    print("Student " + name + "'s lab took too long.")
                            else:
                                try:
                                    result = run(["./" + local_name_dir + "/" + lab_name], timeout=timeout, stdout=PIPE, stderr=PIPE, universal_newlines=True, input=proc_input if use_proc_input else None)
                                    output = result.stdout
                                    log = open(local_name_dir + "/output.log", "w")
                                    log.write(output)
                                    log.close()
                                except TimeoutExpired:
                                    print("Student " + name + "'s lab took too long.")
                           


'

def main(lab_name, grader):

    # grab command params, and sanitize them
    re.sub(r'\W+', '', lab_name)
    if (lab_name == "help" or not sys.argv[1] or not sys.argv[2]):
        help()
    re.sub(r'\W+', '', grader)
    args = None
    if len(sys.argv) > 3:
        args = sys.argv[3]
    execute_compilation = True
    compile_submission = True
    make_submission = False
    use_proc_input = False
    check_attendance = False
    clear_previous_labs = True

    with open('config.toml', 'r') as f:
        config = toml.load(f)

    # related to check attendance

    proc_input = None

    # -x avoids running the compiled output (useful for user input)
    if args is not None:
        if 'x' in args:
            execute_compilation = False
        if 'X' in args:
            compile_submission = False
        if 'm' in args:
            make_submission = True
        if "n" in args:
            clear_previous_labs = False
        if 's' in args and len(sys.argv) > 3:
            use_proc_input = True
            proc_input = sys.argv[4]
        if 'a' in args and len(sys.argv) > 3:
            check_attendance = True
            if use_proc_input == True:
                global course_id
                course_id = sys.argv[5]
                global token
                token = sys.argv[6]
            else:
                course_id = sys.argv[4]
                token = sys.argv[5]
            
    cache_dir = config['paths']['cache_dir']
    global cache_path 
    global hellbender_lab_directory 
    hellbender_lab_directory = config['paths']['hellbender_lab_dir']
    local_directory_name = config['general']['class_code'] + config['paths']['local_storage_dir']
    cache_path = local_directory_name + "/" + cache_dir
    token = config['canvas']['api_token']
    lab_path = gen_directories(main_dir = local_directory_name, cache_dir = cache_dir, lab_name = lab_name, check_attendance = check_attendance, make_submission=make_submission, course_id=course_id, token=token, clear_previous_labs=clear_previous_labs)
    perform_backup(main_dir = local_directory_name, lab_name=lab_name, param_lab_path = lab_path, grader=grader, compile_submission=compile_submission, execute_compilation=execute_compilation, use_proc_input=use_proc_input, check_attendance=check_attendance, make_submission = make_submission, clear_previous_labs=clear_previous_labs, proc_input = proc_input)

if __name__ == "__main__":
    if (len(sys.argv) < 3):
        help()
    main(sys.argv[1], sys.argv[2])