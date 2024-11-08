import streamlit as st
from streamlit import session_state as ss
from streamlit_cookies_controller import CookieController
import time
import pyemvue
from pyemvue.enums import Scale, Unit

import pandas as pd
import datetime
from plotly import express as px

# Inspiration from ; https://discuss.streamlit.io/t/new-component-streamlit-cookies-controller/64251/9

cookie_name = st.secrets['COOKIE_NAME']
controller = CookieController(key='cookies')

new_data_ready = False

# def authenticate():
#     usern = ss.username
#     passw = ss.password

#     login_res = ss.vue.login(username=usern, password=passw)#, token_storage_file='keys.json')
#     st.write(f"login res: {login_res}")

if 'vue' not in ss:
    print("Instantiating Vue")
    ss.vue = pyemvue.PyEmVue()
    ss.login = None

def login_click():
    print(f"creds {ss.username} {ss.password}")
    ss.login = ss.vue.login(username=ss.username, password=ss.password )#, token_storage_file='keys.json')
    print(f"login attempt: {ss.login}")
    print(ss.vue.__dict__)
    return

with st.sidebar:
    username = st.text_input("Vue User", key="username")
    password = st.text_input("Vue Password", key="password", type="password")
    login = st.button("Login", on_click=login_click)


# # Newly opened app or user reloads the page.
# if 'login_ok' not in ss:

#     # Check the contents of cookie.
#     cookies = controller.getAll()
#     time.sleep(1)

#     # Get cookie username and password if there is.
#     cookie_username = controller.get(f'{cookie_name}_username')
#     cookie_password = controller.get(f'{cookie_name}_password')

#     if cookie_username and cookie_password:
#         # ss.login_ok = True
#         ss.username = cookie_username
#         ss.password = cookie_password

def print_recursive(usage_dict, info, depth=0):
    for gid, device in usage_dict.items():
        for channelnum, channel in device.channels.items():
            name = channel.name
            if name == 'Main':
                name = info[gid].device_name
            print('-'*depth, f'{gid} {channelnum} {name} {channel.usage} kwh')
            if channel.nested_devices:
                print_recursive(channel.nested_devices, info, depth+1)

status = st.status("Status")


def runme():
    device_gids = []
    device_info = {}
    for device in ss.devices:
        if not device.device_gid in device_gids:
            device_gids.append(device.device_gid)
            device_info[device.device_gid] = device
        else:
            device_info[device.device_gid].channels += device.channels

    device_usage_dict = ss.vue.get_device_list_usage(deviceGids=device_gids, instant=None, scale=Scale.MINUTE.value, unit=Unit.KWH.value)
    print('device_gid channel_num name usage unit')
    print_recursive(device_usage_dict, device_info)

debug = st.container(border=True)

st.button("Print tree", on_click=runme)

with debug:
    if 'username' in ss:
        st.write(f"username: {ss.username}")
    if 'login' in ss:
        st.write(f"login: {ss.login}")
    st.write(f"vue: {ss.vue.__dict__}")

def fetch_plot_data():
    ss.df = pd.DataFrame()
    data = []
    scale = "1H"
    print(f"\r\nProcessing {len(ss.devices)} devices")
    for device in ss.devices:
        print(f"Processing device {device['device_name']}")
        if device['device_name'] == "":
            print(f"Skipping: |{device['device_name']}|")
            continue
        print(f"  Processing {len(device['channels'])} channels")
        for channel in device['channels']:
            print(f"   >{device['device_name']} {channel['name']} {channel['channel_type_gid']} {channel['channel_num']}")
            usage_over_time, start_time = ss.vue.get_chart_usage(channel, datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=7*4), datetime.datetime.now(datetime.timezone.utc), scale=scale, unit=Unit.KWH.value)
            time_range = pd.date_range(start_time, freq='1h', periods=len(usage_over_time)).values
            _df = pd.DataFrame({"time":time_range, "usage":usage_over_time})
            _df["device"] = device['device_name']
            _df["channel"] = channel['name']
            ss.df = pd.concat([ss.df, _df])
    ss.df.reset_index(inplace=True)
    # ss.df.drop(ss.df[ss.df["channel"] == "solar right"].index, inplace=True)
    # ss.df.drop(ss.df[ss.df["channel"] == "solar right 2"].index, inplace=True)
    # ss.df.loc[(ss.df['channel'].str.contains('solar')) & (~ss.df.usage.isna()), 'usage'] = abs(ss.df[(ss.df['channel'].str.contains('solar')) & (~ss.df.usage.isna())]['usage'])*-1


def plotnow():
    p = px.bar(ss.df, x="time", y="usage", color="channel")
    print(ss.df.head())
    print('plotting')
    st.plotly_chart(p)

def refresh_vue_data():
    print("Fetching data")
    raw_devices = ss.vue.get_devices()
    print(f"Captured {len(raw_devices)} devices")
    
    ss.devices = {}

    ss.device_totals = {}

    for device in raw_devices:
        dict_device = device.__dict__
        gid = dict_device['device_gid']

        if gid not in ss.devices: ss.devices[gid] = {}

        if  dict_device['firmware'] == None: # This has all the channels, no meta
            if 'channels' in ss.devices[gid]:
                ss.devices[gid]['channels'].extend(dict_device['channels']) 
            else:
                ss.devices[gid]['channels'] = dict_device['channels']
            ss.devices[gid]['HAS_CHANNELS'] = True

        if dict_device['firmware'] != None: # This has all the meta and one None channel (which is the total)
            _meta = dict_device.copy()
            _meta.pop('channels') if 'channels' in _meta else None
            ss.devices[gid].update(_meta)
            # ss.devices[gid]['channels'].extend(dict_device['channels']) ## maybe move this to its own key?
            ss.device_totals[gid] = dict_device['channels']
            ss.devices[gid]['HAS_META'] = True
    for gid, dev in ss.devices.items():
        print("")
        print(dev)
        _channels = []
        for c in dev['channels']:
            print("ASDFASDF")
            print(c)
            _channels.append(c.name)
        print(f" dev {dev['device_name']}: {_channels}")
    ss.channel_types = ss.vue.get_channel_types()
    status.write("Fetching plot data")
    fetch_plot_data()
    status.write("Plot data fetch complete")

def check_data_ready():
    if 'devices' not in ss:
        return False
    if 'channel_types' not in ss:
        return False
    if 'df' not in ss:
        return False
    return True

if not check_data_ready():
    refresh_vue_data()
    new_data_ready = True

if new_data_ready == True:
    plotnow()
    new_data_ready = False
st.button("refresh data", on_click=refresh_vue_data)
st.button("force plot", on_click=plotnow)

if 'df' in ss:
    st.dataframe(ss.df, height=250)



