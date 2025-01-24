# CS 1050 Backup Script 
# Matt Marlow 
import os 
import shutil
import sys
import re
import requests
import json
import toml
import datetime

from subprocess import PIPE, run, STDOUT, Popen, TimeoutExpired
from csv import DictReader, DictWriter
from pathlib import Path

class Config: 
    def __init__(self, class_code, execution_timeout, roster_invalidation_days, local_storage_dir, hellbender_lab_dir, cache_dir, api_prefix, api_token, course_id, attendance_assignment_name_scheme):
        self.class_code = class_code
        self.execution_timeout = execution_timeout
        self. roster_invalidation_days = roster_invalidation_days
        self.local_storage_dir = local_storage_dir
        self.hellbender_lab_dir = hellbender_lab_dir
        self.cache_dir = cache_dir
        self.api_prefix = api_prefix
        self.api_token = api_token
        self.course_id = course_id
        self.attendance_assignment_name_scheme = attendance_assignment_name_scheme
class CommandArgs:
    def __init__(self, lab_name, grader_name, execute_compilation = True, compile_submission = True, make_submission = False,
    use_proc_input = False, proc_input = None, check_attendance = False, clear_previous_labs = True):
        self.lab_name = lab_name
        self.grader_name = grader_name
        self.execute_compilation = execute_compilation
        self.compile_submission = compile_submission
        self.make_submission = make_submission
        self.use_proc_input = use_proc_input
        self.proc_input = proc_input
        self.check_attendance = check_attendance
        self.clear_previous_labs = clear_previous_labs


class Context:
    def __init__(self, config_obj, command_args_obj):
        self.config_obj = config_obj
        self.command_args_obj = command_args_obj



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
# Get individual submission of assignment from Canvas and determine if the score matches the criteria
def get_assignment_score(assignment_id, user_id, score_criteria):
        canvas_assignments_submission_api = canvas_api_prefix + "courses/" + str(course_id) + "/assignments/" + str(assignment_id) + "/submissions/" + str(user_id)
        response = make_api_call(canvas_assignments_submission_api, token)
        if response is not None:
            if (response.json()['entered_score'] >= score_criteria):
                return True
        return False
# Generates a roster based on the grader's group on Canvas. 
def generate_grader_roster(context):
    config_obj = context.config_obj
    command_args_obj = context.command_args_obj
    csv_rosters_path = config_obj.hellbender_lab_dir + config_obj.class_code + "/csv_rosters"
    fieldnames = ['pawprint', 'canvas_id', 'name', 'date']
    # first we'll check if the roster already exists.
    if Path(csv_rosters_path + "/" + command_args_obj.grader_name + ".csv").stat().st_size != 0:
        invalidation_date = datetime.datetime.now() - datetime.timedelta(days=config_obj.roster_invalidation_days)
        # if it does, let's see how old it is
        # every student has a date appended to it which should be the same so we'll just check the first one
        with open(csv_rosters_path + "/" + command_args_obj.grader_name + ".csv", 'r', newline='') as csvfile:
            reader = DictReader(csvfile, fieldnames=fieldnames)
            next(reader) # consume header
            sample_row = next(reader)
            stored_date_str = sample_row['date']
            stored_date_obj = datetime.datetime.strptime(stored_date_str, "%Y-%m-%d %H:%M:%S.%f")
            invalidation_date = datetime.datetime.now() - datetime.timedelta(days=config_obj.roster_invalidation_days)
            if (stored_date_obj > invalidation_date):
                print("Roster data is recent enough to be used")
                return
    print("Preparing roster data")
    # firstly, get a list of groups
    group_api = config_obj.api_prefix + "courses/" + str(config_obj.course_id) + "/groups"
    groups = make_api_call(group_api, config_obj.api_token)
    # we need to find the group ID corresponding to the invoked grader
    group_id = -1
    for key in groups.json():
        if key['name'] == command_args_obj.grader_name:
            group_id = key['id'] 
    # if it's still -1, we didn't find it. program will probably crash at some point but we're not going to exit because maybe a cached copy exists?
    if group_id == -1: 
        print("A group corresponding to " + command_args_obj.grader_name + " was not found in the Canvas course " + str(config_obj.course_id))
    # now we can retrieve a list of the users in the grader's group
    group_api = config_obj.api_prefix + "groups/" + str(group_id) + "/users"
    users_in_group = make_api_call(group_api, config_obj.api_token)

    if not os.path.exists(csv_rosters_path):
        os.makedirs(csv_rosters_path)
    with open(csv_rosters_path + "/" + command_args_obj.grader_name + ".csv", 'w', newline='') as csvfile:
        writer = DictWriter(csvfile, fieldnames = fieldnames)
        writer.writeheader()
        data = []
        for key in users_in_group.json():
            dict = {'pawprint': key['login_id'], 'canvas_id': key['id'], 'name': key['sortable_name'], 'date': datetime.datetime.now()}
            data.append(dict)
        writer.writerows(data)


# Get list of assignments from Canvas and export to JSON file 
def generate_assignment_list(course_id, token, cache_path):
    canvas_assignments_api = canvas_api_prefix + "courses/" +course_id + "/assignments/"
    response = make_api_call(canvas_assignments_api, token)
    with open(cache_path + "/assignment_list.json", 'w', encoding='utf-8') as file:
        json.dump(response.json(), file, ensure_ascii=False, indent=4)

# Preamble function responsible for generating and prepping any necessary directories and files
def gen_directories(context):
    config_obj = context.config_obj
    command_args_obj = context.command_args_obj
    # "preamble" code - generates the local directories
    complete_local_storage_dir = config_obj.class_code + config_obj.local_storage_dir
    if not os.path.exists(complete_local_storage_dir):
        # create main lab dir
        os.makedirs(complete_local_storage_dir)
        print("Creating main lab dir")
    cache_path = complete_local_storage_dir + "/" + config_obj.cache_dir
    if os.path.exists(cache_path):
        print("A cache folder for the program already exists. Clearing it and rebuilding")
        shutil.rmtree(cache_path)
    print("Generating a cache folder")
    os.makedirs(cache_path)
        
    generate_grader_roster(context)
        # generate_assignment_list(course_id, token, cache_path = main_dir + "/" + cache_dir)
   
    param_lab_dir = command_args_obj.lab_name + "_backup"
    param_lab_path = complete_local_storage_dir + "/" + param_lab_dir
    # double check if the backup folder for the lab exists and if it does, just clear it out and regenerate
    # could also ask if the user is cool with this
    print("Checking path ", param_lab_path)
    if os.path.exists(param_lab_path) and command_args_obj.clear_previous_labs:
        print("A backup folder for", command_args_obj.lab_name, " already exists. Clearing it and rebuilding")
        shutil.rmtree(param_lab_path)
    print("Creating a backup folder for", command_args_obj.lab_name)
    os.makedirs(param_lab_path)
    if command_args_obj.make_submission:
        p = Popen(['cs1050start', command_args_obj.lab_name], cwd=config_obj.local_storage_dir )
        p.wait()
    return param_lab_path

def perform_backup(context):
    # locate the directories for submissions dependent on grader
    # also find the pawprints list for the grader
    config_obj = context.config_obj
    command_args_obj = context.command_args_obj
    grader_csv = config_obj.hellbender_lab_dir + config_obj.class_code + "/csv_rosters/" + command_args_obj.grader_name + ".csv"
    submissions_dir = config_obj.hellbender_lab_dir + config_obj.class_code  + "/submissions/" + command_args_obj.lab_name + "/" + command_args_obj.grader_name
    local_name_dir = config_obj.class_code + config_obj.local_storage_dir
    attendance_assignment_id = None
    # if attendance is true, then we need to go find the assignment we need
    if command_args_obj.check_attendance == True:
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
        fieldnames = ['pawprint', 'canvas_id', 'name', 'date']
        csvreader = DictReader(pawprints_list, fieldnames=fieldnames)
        # for each name, we need to check if there's a valid submission
        for row in csvreader:
            # sanitize pawprint for best results
            pawprint = row['pawprint']
            pawprint = re.sub(r'\W+', '', pawprint)
            pawprint = pawprint.replace("\n", "")
            name = row['name']
            canvas_id = None
             
            if command_args_obj.check_attendance  == True:
                canvas_id = map_pawprint_to_user_id(pawprint)
                if not get_assignment_score(attendance_assignment_id, canvas_id, 1):
                    print(name + " was marked absent during the lab session and does not have a valid submission.")
                    continue
            pawprint_dir = submissions_dir + "/" + pawprint
            if (command_args_obj.clear_previous_labs == False):
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
                           
def main(lab_name, grader):

    # grab command params, and sanitize them
    re.sub(r'\W+', '', lab_name)
    if (lab_name == "help" or not sys.argv[1] or not sys.argv[2]):
        help()
    re.sub(r'\W+', '', grader)
    args = None
    if len(sys.argv) > 3:
        args = sys.argv[3]

    # prepare initial command arguments 
    command_args_obj = CommandArgs(lab_name, grader, execute_compilation = True, 
    compile_submission = True, make_submission = False, use_proc_input = False,
    check_attendance = False, clear_previous_labs = True) 

    with open('config.toml', 'r') as f:
        config = toml.load(f)
    # prepare configuration options
    config_obj = Config(config['general']['class_code'], config['general']['execution_timeout'], config['general']['roster_invalidation_days'],
    config['paths']['local_storage_dir'], config['paths']['hellbender_lab_dir'], config['paths']['cache_dir'], 
    config['canvas']['api_prefix'], config['canvas']['api_token'], config['canvas']['course_id'], config['canvas']['attendance_assignment_name_scheme'])


    # -x avoids running the compiled output (useful for user input)
    if args is not None:
        if 'x' in args:
            command_args_obj.execute_compilation = False
        if 'X' in args:
            command_args_obj.compile_submission = False
        if 'm' in args:
            command_args_obj.make_submission = True
        if "n" in args:
            command_args_obj.clear_previous_labs = False
        if 's' in args and len(sys.argv) > 3:
            command_args_obj.use_proc_input = True
            command_args_obj.proc_input = sys.argv[4]
        if 'a' in args and len(sys.argv) > 3:
            command_args_obj.check_attendance = True
            

    context = Context(config_obj, command_args_obj)
    lab_path = gen_directories(context)
    perform_backup(context)

if __name__ == "__main__":
    if (len(sys.argv) < 3):
        help()
    main(sys.argv[1], sys.argv[2])