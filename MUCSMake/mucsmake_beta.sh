#!/bin/bash

orig_dir=$(pwd)

# Assume the file argument is the third parameter
input_file="$3"
# If the provided file path is not absolute, convert it
if [[ "$input_file" != /* ]]; then
    input_file="$orig_dir/$input_file"
fi

# Change directory to where the script is located
cd "$(dirname "$0")"

# Activate the virtual environment
source .venv/bin/activate

python3 mucsmake.py $1 $2 "$input_file"
deactivate