from cx_Freeze import setup, Executable

# Replace 'your_script.py' with the name of your Python script
executables = [Executable('chunkone_service.py')]
options = {
    'build_exe': {
        'packages': ['gspread'],  # List any additional packages to include
        'include_files': ['credentials.json'],  # List any additional data files to include
    }
}
setup(
    name='YourAppName',
    version='1.0',
    description='Your application description',
    executables=executables,
    options=options
)