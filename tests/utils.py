import re
from django.test.client import encode_multipart


def replace_variables_in_string(string, parameters):
    matches = re.findall("<<(\w+?)>>", string)
    for match in matches:
        string = string.replace(f"<<{match}>>", parameters[match])
    return string


def create_form_content(data):
    boundary_string = 'BoUnDaRyStRiNg'
    content = encode_multipart(boundary_string, data)
    content_type = 'multipart/form-data; boundary=' + boundary_string
    return content, content_type
