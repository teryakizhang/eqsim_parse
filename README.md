# eqsim_parse
Extract and process certain important information from eQuest simlation output file (SIM). The basis of the code is pulled from [jmarrec's eQSimParsing](https://github.com/jmarrec/eQSimParsing). 


### Installation
The following installations and commands will be necessary before the script is able to run. 

This script requires [Python](https://www.python.org/) V3+ to run. Make sure you have it installed first.

Compatible version: Python 3.6+

Following are commands to run in your command prompt to install the dependencies.
```
pip install pandas
```

You should be good to go now. 

### Running the script
* Locate where you downloaded the script and move the SIM file you want to process into the same directory
* Open command prompt from start
* Navigate to where you downloaded the script using `CD C:\Users\where you downloaded the script`. You can copy and paste from navigation bar of Explorer
* Use the command `python parse-sim.py`
* Voila, your CSVs should be there
