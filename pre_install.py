import os

install_path = 'c:/ProgramData/AIBS_MPE/ShotgunAnatomy'

os.makedirs(install_path, exist_ok = True)
os.makedirs(install_path + '/logs', exist_ok = True)
os.makedirs(install_path + '/database', exist_ok = True)
os.makedirs(install_path + '/database/acquisitions', exist_ok = True)
os.makedirs(install_path + '/database/protocols', exist_ok = True)
os.makedirs(install_path + '/database/calibrations', exist_ok = True)

