import os
from dotenv import load_dotenv
import api_pb2 as protocol
import csv
import requests
import copy
from google.protobuf.json_format import MessageToDict
from captcha.imagetyperzapi import ImageTyperzAPI
from time import sleep

headers_protobuf = {
    'Accept': 'application/x-protobuf',
    'Content-Type': 'application/x-protobuf',
    'persistent-device-id': '',
    'X-Auth-Token': '',
    'platform': 'web',
    'Referer': 'https://tinder.com/',
    'Connection': 'keep-alive'
}

headers_json = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'platform': 'web',
    'Referer': 'https://tinder.com/',
    'Connection': 'keep-alive'
}

account_format = {
    'X-Auth-Token' : '',
    'refresh-token': '',
    'persistent-device-id': '',
    'proxy-formatted': '',
    'proxy': '',
    'captcha-tries': 0
}

proxy_template = {
    'http': 'http://{fuser}:{fpass}@{fhost}:{fport}',
    'https': 'http://{fuser}:{fpass}@{fhost}:{fport}',
}

def solve_captcha(data, proxy):
    ita = ImageTyperzAPI(CAPTCHA_TOKEN)

    balance = ita.account_balance()
    print('Balance: {}'.format(balance))

    captcha_params = {
        'page_url': 'https://tinder.com',
        'sitekey': 'EBC0462E-1FD4-25CD-A21E-A68A0E5DDB23',
        's_url': 'https://tinder-api.arkoselabs.com',
        'data': f"{{\"blob\":\"{data}\"}}",
        'proxy': proxy,    # optional, or 126.45.34.53:123:joe:password
        # 'user_agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0',    # optional
    }
    captcha_id = ita.submit_funcaptcha(captcha_params)

    print('Waiting for captcha to be solved ...')
    response = None
    while not response:
        sleep(5)
        response = ita.retrieve_response(captcha_id)
    return response

def handle_captcha(account, ban_appeal):
    account['captcha-tries'] += 1
    if account['captcha-tries'] > 1:
        print("Could not solve captcha. Skipping")
        return False
    
    captcha_response = solve_captcha(ban_appeal['arkoseDataBlob'], account['proxy'])
    print(f"Captcha status for token {account['refresh-token']}: {captcha_response['Status']}")
    if captcha_response['Status'] == 'Solved':
        challenge_answer = captcha_response['Response']
        challenge_token = ban_appeal['challengeToken']

        try:
            response = requests.post(
                "https://api.gotinder.com/challenge/verify?locale=en",
                data={
                    'challenge_answer': challenge_answer,
                    'challenge_token': challenge_token,
                    'challenge_type': 'arkose'
                    },
                proxies=account['proxy-formatted']
                )
        except requests.exceptions.RequestException:
            print(f"Could not send request. Most likely proxy error \n{account['X-Auth-Token']},{account['refresh-token']},{account['persistent-device-id']},{account['proxy']}")
            return False
        
        print("Verify challenge code", response.status_code)
        if response.status_code != 200:
            return False
        return True
    else:
        print("Failed to solve challenge")
    
def encode(refresh_token):
    request = protocol.AuthGatewayRequest()
    request.refresh_auth.refresh_token = refresh_token
    encoded = request.SerializeToString()

    return encoded

def decode(bytes_received):
    response = protocol.AuthGatewayResponse()
    response.ParseFromString(bytes_received)
    dict_obj = MessageToDict(response)
    return dict_obj

def refresh_token(account):
    request_data = encode(account['refresh-token'])

    headers_protobuf['persistent-device-id'] = account['persistent-device-id']
    headers_protobuf['X-Auth-Token'] = account['X-Auth-Token']

    try:
        response = requests.post(
            "https://api.gotinder.com/v3/auth/login?locale=en",
            headers=headers_protobuf,
            data=request_data,
            proxies=account['proxy-formatted'],
            allow_redirects=False
        )
    except requests.exceptions.RequestException:
        print(f"Could not send request. Most likely proxy error \n{account['X-Auth-Token']},{account['refresh-token']},{account['persistent-device-id']},{account['proxy']}")
        with open('failed_tokens.csv', 'a', newline='') as file:
            fieldnames = ['X-Auth-Token', 'refresh-token', 'persistent-device-id', 'proxy-formatted', 'proxy', 'captcha-tries']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerow(account)
        print("====================")
        return
    
    print(f"Token {account['refresh-token']} | Response status: {response.status_code}")
    if response.content:
        decoded_message = decode(response.content)
        if response.status_code == 200:
            print("Response:", decoded_message)
            print("====================")
            return decoded_message['loginResult']['authToken']
        elif response.status_code == 403:
            print("Response:", decoded_message)
            if decoded_message['error']['code'] == 40307:
                print(f"Token {account['refresh-token']} needs captcha")
                solved = handle_captcha(account, decoded_message['error']['banReason']['banAppeal'])
                if solved:
                    new_token = refresh_token(account)
                    return new_token
            if decoded_message['error']['code'] == 40324:
                print("Account is selfie banned. Skipping")
        elif response.status_code == 401:
            print("Unauthorized. Check \"persistent-device-id\"")
            print("Response:", decoded_message)
        else:
            print("Bad request")
        
    print("====================")
    return

def main():
    load_dotenv(override=True)

    global CAPTCHA_TOKEN
    try:
        CAPTCHA_TOKEN = os.getenv("CAPTCHA_TOKEN")
        if CAPTCHA_TOKEN == None:
            raise TypeError
        elif CAPTCHA_TOKEN[0:2] == '':
            raise ValueError
    except ValueError:
        print("CAPTCHA_TOKEN is in wrong format")
        quit()
    except TypeError:
        print("Environment file not found. Creating one, please check it!")
        with open('.env', 'w') as file:
            file.writelines(['CAPTCHA_TOKEN=\n', 'CAPTCHA_TOKEN='])
        quit()

    print("====================\nTinder API Token Refresher\n====================")

    account_list = []
    total_accounts = 0
    accounts_updated = 0

    with open('input.csv', 'r') as file:
        print("Parsing input data\n====================")
        csv_reader = csv.reader(file, delimiter=',')

        is_on_first_line = True
        try:
            for row in csv_reader:
                if not is_on_first_line:
                    account = copy.deepcopy(account_format)    

                    account['X-Auth-Token'] = row[0]
                    account['refresh-token'] = row[1]
                    account['persistent-device-id'] = row[2]
                    account['proxy'] = row[3]

                    proxy_string = row[3].split(':')
                    proxy_dict = copy.deepcopy(proxy_template)
                    proxy_dict['http'] = proxy_dict['http'].format(fuser=proxy_string[2],
                                                                   fpass=proxy_string[3],
                                                                   fhost=proxy_string[0],
                                                                   fport=proxy_string[1])
                    
                    proxy_dict['https'] = proxy_dict['http']                
                    account['proxy-formatted'] = proxy_dict

                    account_list.append(account)           
            
                is_on_first_line = False
            
            total_accounts = len(account_list)
            print("Found", total_accounts, "accounts")

        except Exception as e:
            print("Improper input data format")
            raise SystemExit(e)
    
    print("Loaded accounts:")
    for i in range(len(account_list)):
        print("Token", account_list[i]['refresh-token'], "Proxy", account_list[i]['proxy'])

    print("====================")

    i = 0
    while i < len(account_list):
        new_auth_token = refresh_token(account_list[i])
        del account_list[i]['proxy-formatted']
        del account_list[i]['captcha-tries']
        if new_auth_token != None:
            account_list[i]['X-Auth-Token'] = new_auth_token
            accounts_updated += 1
            i += 1
        else:
            account_list.pop(i)

    with open('input.csv', 'w', newline='') as file:
        fieldnames = ['X-Auth-Token', 'refresh-token', 'persistent-device-id', 'proxy']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        
        writer.writeheader()
        writer.writerows(account_list)
        print(f"Wrote new tokens to file. Updated {accounts_updated}/{total_accounts}")

if __name__ == "__main__":
    main()