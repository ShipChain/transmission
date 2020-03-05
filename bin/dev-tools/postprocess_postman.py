#! /usr/bin/env python

import json
import sys


def postprocess_postman(src_path, dest_path):
    with open(src_path, "r") as json_file:
        data = json.load(json_file)

    data['variable'][0]['value'] = '{{transmission_url}}'

    iterate_over_nested_items(data['item'])

    for item in data['item']:
        if item['name'] == 'Generate Token':
            item['request']['body']['formdata'][0]['value'] = '{{jwt_username}}'
            item['request']['body']['formdata'][1]['value'] = '{{jwt_password}}'
            item['request']['body']['formdata'][2]['value'] = 892633
            item['request']['body']['formdata'][3]['value'] = 'password'
            item['request']['body']['formdata'][4]['value'] = 'openid email permissions'
            item['request']['body']['formdata'][5]['disabled'] = True

    data['event'] = [
        {
            "listen": "prerequest",
            "script": {
                "id": "9f01f1ab-7a96-449d-9fbc-37072acf9b18",
                "type": "text/javascript",
                "exec": [
                    "var token_time = pm.environment.get(\"token_time\");",
                    "var now_time = new Date().getTime();",
                    "",
                    "var token_age = now_time - token_time;",
                    "",
                    "if(token_age > 60000){",
                    "",
                    "    var url = pm.environment.get(\"profiles_url\");",
                    "    var clientId = pm.environment.get(\"oidc_client_id\");",
                    "    var usr = pm.environment.get(\"jwt_username\");",
                    "    var pwd = pm.environment.get(\"jwt_password\");",
                    "    ",
                    "    pm.sendRequest(",
                    "    {",
                    "        url: url+\"/openid/token/\",",
                    "        method: 'POST',",
                    "        body: {",
                    "            mode: 'formdata',",
                    "            formdata: [",
                    "                {key: \"client_id\", value: clientId, disabled: false, "
                    "description: {content:\"\", type:\"text/plain\"}},",
                    "                {key: \"username\", value: usr, disabled: false, "
                    "description: {content:\"\", type:\"text/plain\"}},",
                    "                {key: \"password\", value: pwd, disabled: false, "
                    "description: {content:\"\", type:\"text/plain\"}},",
                    "                {key: \"grant_type\", value: 'password', disabled: false, "
                    "description: {content:\"\", type:\"text/plain\"}},",
                    "                {key: \"scope\", value: 'openid email permissions', disabled: false, "
                    "description: {content:\"\", type:\"text/plain\"}},",
                    "            ]",
                    "        }",
                    "    }",
                    "    , function (err, response) {",
                    "        var data = response.json();",
                    "        pm.environment.set(\"token\", data.id_token);",
                    "        pm.environment.set(\"token_time\", now_time);",
                    "    });",
                    "}",
                    "",
                    "else {",
                    "    console.log(\"Existing token reused. [\"+(token_age/1000)+\"]\")",
                    "}"
                ]
            }
        },
        {
            "listen": "test",
            "script": {
                "id": "d00cedd1-60ca-4bb5-a942-77dfc3249b26",
                "type": "text/javascript",
                "exec": [
                    ""
                ]
            }
        }
    ]

    with open(dest_path, "w") as json_file:
        json.dump(data, json_file)


# This iterates over nested item in order to ensure all query parameters are disabled and the token is in the header
def iterate_over_nested_items(calls):
    if isinstance(calls, list):
        for call in calls:
            iterate_over_nested_items(call)

    if 'item' in calls:
        if not isinstance(calls['item'], list):
            iterate_over_nested_items(calls['item'])
        else:
            for call in calls['item']:
                iterate_over_nested_items(call)

    elif not isinstance(calls, list):
        modify_call(calls)


def modify_call(call):
    call['request'] = add_header(call)
    if 'query' in call['request']['url']:
        call['request']['url']['query'] = disable_query(call)
    if 'auth' in call['request']:
        call['request'].pop('auth')
    return call


def add_header(call):
    if 'header' in call['request']:
        call['request']['header'].append({
            "key": "Authorization",
            "value": "JWT {{token}}"
        })
    else:
        call['request']['header'] = [{
            "key": "Authorization",
            "value": "JWT {{token}}"
        }]
    return call['request']


def disable_query(call):
    queries = []

    if 'query' in call['request']['url']:
        queries = call['request']['url']['query']

    for query in queries:
        query['disabled'] = True

    return queries


postprocess_postman(sys.argv[1], sys.argv[2])
