import requests
import time
import csv
import multiprocessing
import zstandard as zstd
from datetime import datetime
import certifi
import json
import copy
import os
from openai import OpenAI
import time
import logging
from queue import Empty
from typing import List, Tuple, Any
from multiprocessing.pool import Pool
import multiprocessing
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from concurrent.futures import TimeoutError
from dotenv import load_dotenv

TEMP_ENDPOINT = "https://api.gotinder.com/v2/profile?locale=en&include=account%2Cavailable_descriptors%2Cboost%2Cbouncerbypass%2Ccontact_cards%2Cemail_settings%2Cfeature_access%2Cinstagram%2Clikes%2Cprofile_meter%2Cnotifications%2Cmisc_merchandising%2Cofferings%2Conboarding%2Cpaywalls%2Cplus_control%2Cpurchase%2Creadreceipts%2Cspotify%2Csuper_likes%2Ctinder_u%2Ctravel%2Ctutorials%2Cuser%2Call_in_gender"
PROFILE_LIST_ENDPOINT = "https://api.gotinder.com/v2/recs/core?locale=en&limit=100"
PASS_ENDPOINT = "https://api.gotinder.com/pass/{id}?locale=en&s_number={s_number}"
LIKE_ENDPOINT = "https://api.gotinder.com/like/{id}?locale=en&s_number={s_number}"

current_date = datetime.now()

#Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

#Parsing env
load_dotenv(override=True)

try:
    global OPENAI_API_KEY
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY == None:
        raise TypeError
    elif OPENAI_API_KEY[0:2] != 'sk':
        raise ValueError
except ValueError:
    logger.critical("OPENAI_API_KEY is in wrong format")
    quit()
except TypeError:
    logger.critical("Environment file not found. Creating one, please check it!")
    with open('.env', 'w') as file:
        file.writelines(['OPENAI_API_KEY=\n', 'CAPTCHA_TOKEN='])
    quit()

proxy_template = {
    'http': 'http://{fuser}:{fpass}@{fhost}:{fport}',
    'https': 'http://{fuser}:{fpass}@{fhost}:{fport}',
}

headers_template = {
            'X-Auth-Token': 'placeholder', 
            'persistent-device-id': 'placeholder',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
            'Accept': 'application/json',
            'Accept-Language': 'en,en-US',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://tinder.com/',
            'Origin': 'https://tinder.com',
            'Sec-GPC': '1',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
            'app-version': '1054501',
            'tinder-version': '5.45.1',
            'x-supported-image-formats': 'jpeg',
            'platform': 'web',
            'support-short-video': '1',
            'Priority': 'u=4',
            'Connection': 'keep-alive',
            'TE': 'trailers',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
}

account_format = {
    'X-Auth-Token' : '',
    'refresh-token': '',
    'persistent-device-id': '',
    'proxy': ''
}

def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def getProfileList(account, timeout=30):
    headers = copy.deepcopy(headers_template)
    headers['X-Auth-Token'] = account['X-Auth-Token']
    headers['persistent-device-id'] = account['persistent-device-id']
    
    status = -1
    session = create_session()
    
    try:
        r = session.get(
            PROFILE_LIST_ENDPOINT, 
            proxies=account['proxy'], 
            headers=headers, 
            stream=True, 
            verify=certifi.where(),
            timeout=timeout
        )
        status = r.status_code
        
        if status == 429:
            (f"Account {headers['X-Auth-Token']} is rate limited, removing.")
        elif status == 401:
            logger.error(f"Token for Refresh: {account['refresh-token']} is bad or expired, removing.")
        elif status != 200:
            logger.error(f"Non-200 status code {status} for token {headers['X-Auth-Token']}")
            return (account, status)
        
        content_encoding = r.headers.get("Content-Encoding", "")

        try:
            with open(f"logs/data_{headers['X-Auth-Token']}.txt", "w", encoding="utf-8") as output_file:
                if "zstd" in content_encoding:
                    dctx = zstd.ZstdDecompressor()
                    with dctx.stream_reader(r.raw) as reader:
                        buffer = b""
                        while True:
                            try:
                                chunk = reader.read(1024)
                                if not chunk:
                                    break
                                buffer += chunk
                            except Exception as e:
                                logger.error(f"Error reading chunk: {str(e)}")
                                raise Exception
                            
                        try:
                            content = buffer.decode('utf-8', 'ignore')
                            json_data = json.loads(content) 

                            for profile in json_data['data']['results']:
                                try:
                                    user_data = parse_user(profile)
                                    snap = parse_snap(user_data['bio'])
                                    if snap == '-1':
                                        snap = 'None'

                                    with open(f"bios/data_{headers['X-Auth-Token']}.txt", "a", encoding="utf-8") as bios_file:
                                        bios_file.write(f"found_snap: {snap}, {user_data['name']}, {user_data['age']}, Bio: {user_data['bio']}\n")
                                    
                                    pass_id(user_data['id'], user_data['s_number'], headers, account['proxy'], session=session)
                                    time.sleep(50 / 1000)
                                    
                                except Exception as e:
                                    logger.error(f"Error processing profile: {str(e)}")
                                    continue

                            output_file.write(json.dumps(json_data, indent=4))
                        except json.JSONDecodeError as e:
                            logger.error(f"Error parsing JSON: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error processing content: {str(e)}")

        except Exception as e:
            logger.error(f"Error in file operations: {str(e)}")
        finally:
            session.close()

        logger.info(f"File written successfully for token {account['X-Auth-Token']}.")
        
    except KeyboardInterrupt:
        #print(f"\nInterrupt received while processing {headers['X-Auth-Token']}")
        return (account, -1)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout for token {account['X-Auth-Token']}")
        return (account, 408)        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e} on token {account['X-Auth-Token']}. Check the proxy")
        return (account, 500)
    except Exception as e:
        logger.error(f"Unexpected error for token {account['X-Auth-Token']}: {str(e)}")
        return (account, 500)
    finally:
        if session:
            try:
                session.close()
            except:
                pass

    return (account, status)

def parse_user(profile):
    age = 'age unknown'
    try:
        birthdate = datetime.fromisoformat(profile['user']['birth_date'].replace("Z", "+00:00"))
        age = current_date.year - birthdate.year - ((current_date.month, current_date.day) < (birthdate.month, birthdate.day))
    except KeyError:
        pass

    user_data = {
        'name' : profile['user']['name'],
        'age' : age,
        'id' : profile['user']['_id'],
        's_number' : profile['s_number'],
        'bio' : profile['user']['bio']
    }

    return user_data

def parse_snap(bio, timeout=10):
    if len(bio) < 5:
        return '-1'
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "developer",
                    "content": "Look through this bio and find a Snapchat handle. It might be preceded by a prefix (snap, sc, etc.) or a 👻. If multiple words join them. Reutrn strictly just the handle if solved or -1 otherwise."
                },
                {
                    "role": "user",
                    "content": f"Is there a Snapchat handle here \"\"\"{bio}\"\"\""
                }
            ],
            timeout=timeout
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return '-1'


def pass_id(id, snumber, headers, proxies, session=None, timeout=10):

    should_close_session = False
    if session is None:
        session = create_session()
        should_close_session = True
    
    try:
        r = session.get(
            PASS_ENDPOINT.format(id=id, s_number=snumber),
            proxies=proxies,
            headers=headers,
            verify=certifi.where(),
            timeout=timeout
        )
        
        if r.status_code != 200:
            logger.warning(f"{r.status_code} Failed to pass on token: {headers['X-Auth-Token']}")
        # else:
        #     print(r.status_code, "Passed", id, "on token", headers['X-Auth-Token'])
            
    except KeyboardInterrupt:
        #print(f"\nInterrupt received while passing ID {id}")
        return
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout passing ID {id} for token {headers['X-Auth-Token']}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request failed passing ID {id}: {str(e)} on token {headers['X-Auth-Token']}")
    finally:
        if should_close_session and session:
            try:
                session.close()
            except:
                pass
    
def worker_wrapper(args):
    task, worker_function = args
    try:
        logger.info(f"Starting processing for account: {task['X-Auth-Token']}")
        result = worker_function(task)
        
        if isinstance(result, (list, tuple)) and len(result) == 2:
            _, status = result
            return task, status
            
        logger.error(f"Invalid result format: {result}")
        return task, 0
        
    except Exception as e:
        error_msg = str(e)
        if error_msg:
            logger.error(f"Error in worker_wrapper for {task['X-Auth-Token']}: {error_msg}")
        else:
            #print(f"Empty error caught in worker_wrapper for {task['X-Auth-Token']}")
            pass
        return task, 0

def process_accounts_with_dynamic_pool(account_list: List[str], 
                                     worker_function: callable,
                                     timeout_per_task: int = 20) -> List[Tuple[str, int]]:
    
    n_cores = multiprocessing.cpu_count() * 2
    n_workers = min(len(account_list), n_cores)
    
    results = []
    successful_count = 0
    task_queue = multiprocessing.Manager().Queue()
    
    for account in account_list:
        task_queue.put((account, worker_function))

    logger.info(f"Starting main processing loop with {n_workers} workers")
    
    try:
        with Pool(processes=n_workers, maxtasksperchild=100) as pool:
            pending_tasks = []
            
            while True:
                while len(pending_tasks) < n_workers:
                    try:
                        task_tuple = task_queue.get_nowait()
                        async_result = pool.apply_async(worker_wrapper, (task_tuple,))
                        pending_tasks.append((task_tuple[0], async_result))
                    except Empty:
                        if not pending_tasks:
                            logger.info(f"All tasks completed. Total successful: {successful_count}")
                            return results
                        break
                
                still_pending = []
                for task, async_result in pending_tasks:
                    try:
                        account, status = async_result.get(timeout=timeout_per_task)
                        
                        if status == 200:
                            successful_count += 1
                        results.append((account, status))
                        
                    except TimeoutError:
                        logger.warning(f"Timeout for {task['X-Auth-Token']} - requeueing")
                        task_queue.put((task, worker_function))
                        still_pending.append((task, async_result))
                    except Exception as e:
                        error_msg = str(e)
                        if error_msg:
                            logger.error(f"Error processing {task['X-Auth-Token']}: {error_msg}")
                        else:
                            #print(f"Empty error caught for {task['X-Auth-Token']}")
                            pass
                        still_pending.append((task, async_result))
                
                pending_tasks = still_pending
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received. Shutting down gracefully...")
        if pool:
            logger.info("Terminating worker pool...")
            pool.terminate()
            pool.join()
        logger.info(f"Shutdown complete. Total successful: {successful_count}")
        return results
    except Exception as e:
        logger.error(f"Main loop error: {str(e)}")
        if pool:
            pool.terminate()
            pool.join()
        logger.info(f"Shutdown complete. Total successful: {successful_count}")
        return results
    finally:
        if pool:
            try:
                pool.close()
                pool.join()
            except:
                pass

def main():
    logger.info("Tinder API Snap Scraper")

    try:
        os.mkdir("logs")
        os.mkdir("bios")
        logger.info("Created necessary directories")
    except FileExistsError:
        pass
    except PermissionError:
        logger.error(f"Permission denied: Unable to create necessary directories.")
        quit()
    except Exception as e:
        logger.error(f"An error occurred while creating necessary directories: {e}")
        quit()

    account_list = []

    with open('input.csv', 'r') as file:
        logger.info("Parsing input data")
        csv_reader = csv.reader(file, delimiter=',')

        is_on_first_line = True
        try:
            for row in csv_reader:
                if not is_on_first_line:
                    account = copy.deepcopy(account_format)    

                    account['X-Auth-Token'] = row[0]
                    account['refresh-token'] = row[1]
                    account['persistent-device-id'] = row[2]

                    proxy_string = row[3].split(':')
                    proxy_dict = copy.deepcopy(proxy_template)
                    proxy_dict['http'] = proxy_dict['http'].format(fuser=proxy_string[2],
                                                                fpass=proxy_string[3],
                                                                fhost=proxy_string[0],
                                                                fport=proxy_string[1])
                    
                    proxy_dict['https'] = proxy_dict['http']                    
                    account['proxy'] = proxy_dict

                    account_list.append(account)           
            
                is_on_first_line = False
            
            logger.info(f"Found {len(account_list)} accounts")

        except Exception as e:
            logger.error("Improper input data format")
            raise SystemExit(e)
    
    #Displays accounts successfully loaded
    logger.info("Loaded accounts:")
    for i in range(len(account_list)):
        logger.info(f"Token {account_list[i]['X-Auth-Token']} - Proxy {account_list[i]['proxy']}")

    try:
        while True:
            results = process_accounts_with_dynamic_pool(
                account_list=account_list,
                worker_function=getProfileList,
                timeout_per_task=20
            )        

            succesful_account = []
            for acc, status in results:
                if status == 200:
                    succesful_account.append(acc)
            
            account_list = succesful_account                             
            logger.info(f"Successfully processed {len(account_list)} accounts")

    except KeyboardInterrupt:
        logger.info("\nShutting down from main...")
    finally:
        logger.info("Cleanup complete")      

if __name__ == '__main__':
    main()