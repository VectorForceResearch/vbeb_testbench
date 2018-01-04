import os
import sys
from win32com.client import Dispatch


app_path = 'c:/ProgramData/AIBS_MPE/ShotgunAnatomy'
python_install = sys.base_prefix
launcher_path = python_install + '/Scripts/remington_launcher.exe'
module_path = python_install + '/lib/site-packages/remington'
home_dir = os.path.expanduser('~')
desktop = home_dir + '/Desktop'
wdir = os.path.dirname(launcher_path)
filename = 'remington.lnk'
path = os.path.join(desktop, filename)

shell = Dispatch("WScript.Shell")
shortcut = shell.CreateShortCut(path)
shortcut.TargetPath = launcher_path
shortcut.WorkingDirectory = wdir
shortcut.IconLocation = module_path + '/resources/images/icon.ico'
shortcut.save()

