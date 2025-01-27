# GradingTools

This repository will track any changes for scripts used in the TA grading process for any MUCS-affiliated classes.  

When cloning this repository, you should set up a Python virtual environment to make sure all scripts can work correctly. 
https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/

You should install pip following these instructions. Then you can use `python3 -m pip install -r requirements.txt`. A requirements document is included in this repo. 

Current Tools:
- Backup.py
    - Customizable and powerful backup utility to grab student submissions from backend
    - Can automatically compile, run, and output test data to log
    - Interactive with Canvas for a number of features:
        - Dynamic roster data collection for tracking add/drops
        - Attendance checking 
    - Setup and Use
      - A config.toml should be included. Make sure to populate this configuration with your preferred paths, course data, and Canvas information.
    

    
