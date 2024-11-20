import re

def is_valid_name(name):
    # Regular expression to check for unwanted characters or spaces
    pattern = r'^[A-Za-z]+$'  # Allows only letters (upper and lower case)
    return re.match(pattern, name) is not None


# Test the function
name = input("Enter a name: ")
if is_valid_name(name):
    print("Valid name!")
else:
    print("Invalid name. Name should only contain letters (upper or lower case).")
