from wisepaasdatahubedgesdk.EdgeAgent import EdgeAgent
import wisepaasdatahubedgesdk.Common.Constants as constant
from wisepaasdatahubedgesdk.Model.Edge import EdgeAgentOptions, DCCSOptions, EdgeData, EdgeTag
import json, requests, time, base64, datetime, numpy


class datahub_api_get():
    def __init__(self, usr_name, password, node_id,
                 device_id, tag_name, tag_type, mode,
                 array_size, **kwargs):
        """
        使用API讀寫tag資訊
        Args:
            usr_name (str): dataHUB 登錄用戶名
            password (str): dataHUB 登錄密碼
            node_id (str): dataHUB node ID
            device_id (dict): dataHUB device ID
            tag_name (str): dataHUB tag name
            mode(str): 上傳模式, 'joint', 'image', 'pointcloud'
        """        
        
        # 預先登錄datahub
        self.headers = {'Content-Type': 'application/json'}
        self.session = self.login(usr_name, password)
    
        self.node_id = node_id
        self.device_id = device_id[mode]
        self.tag_name = tag_name
        self.tag_type = tag_type
        self.array_size = array_size

    def login(self, usr_name, password):
        '''Login Datahub'''
        login_json = {
            "username": usr_name,
            "password": password
        }
        login_json = json.dumps(login_json)
        # 構造Session
        session = requests.Session()
        
        url_login = 'https://portal-datahub-greenhouse-eks005.education.wise-paas.com/api/v1/Auth'

        # 在session中發送登錄請求，此後這個session就存儲了cookie
        resp = session.post(url_login, headers = self.headers, data = login_json)
        return session

    def new_tagname(self):
        """
        新建Tag, 根據API機制, 如果已經存在同名的Tag則不會新建
        """        
        new_json = {
            "nodeId": self.node_id,
            "deviceId": self.device_id,
            "tagName": self.tag_name,
            "tagType": self.tag_type,
            "description": 'Plant ID' + self.tag_name.split('_')[-1],
            "readOnly": False,
            "arraySize": self.array_size
        }
        new_json = json.dumps(new_json)
        
        url_new = 'https://portal-datahub-greenhouse-eks005.education.wise-paas.com/api/v1/Tags'
        resp = self.session.post(url_new, headers = self.headers, data = new_json)
        return resp

    def read_last_data(self, index):
        """
        從dataHUB上讀取前次上傳的最後一筆資料
        Args:
            index (str): dataHUB 登錄用戶名
        Returns:
            datahub上指定的內容
        """
        
        # self.new_tagname()
        # index=-1 表示所用的資料類型不是array
        if index == -1:
            search_json = {
                "nodeId": self.node_id,
                "deviceId": self.device_id,
                "tagName": self.tag_name
            }
        else:
            search_json = {
                "nodeId": self.node_id,
                "deviceId": self.device_id,
                "tagName": self.tag_name,
                "index": int(index)
            }
        search_json = json.dumps(search_json)
        url_post = 'https://portal-datahub-greenhouse-eks005.education.wise-paas.com/api/v1/RealData/raw'
        resp = self.session.post(url_post, headers=self.headers, data=search_json)
        print(resp.content)
        return json.loads(resp.content.decode('utf8'))[0]['value']

    def close_connection(self):
        self.session.close()

class datahub_send_data():
    def __init__(self, hyp):
        """
        使用DCCS傳送資料至Datahub
        Args:
            hyp (dict): 運行設定參數
        """        
        self.hyp = hyp
        self.edge_agent = self.connect(hyp)
    
    def connect(self, hyp):
        
        def edgeAgent_on_connected():
            print('Connect success')
        
        options = EdgeAgentOptions(
            nodeId = hyp['node_id'],
            # 節點類型 (Gateway, Device), 預設是 Gateway
            type = constant.EdgeType[hyp['edge_type']],
            # 預設是 60 seconds
            heartbeat = 60,
            # 是否需要斷點續傳, 預設為 true                                   
            dataRecover = True,
            # 連線類型 (DCCS, MQTT), 預設是 DCCS                                    
            connectType = constant.ConnectType[hyp['connect_type']],
            # 若連線類型是 DCCS, DCCSOptions 為必填
            DCCS = DCCSOptions(
                # DCCS API Url
                apiUrl = hyp['api_url'],
                # Creadential key
                credentialKey = hyp['credential_key']
            )
        )
        edge_agent = None
        edge_agent = EdgeAgent(options)
        edge_agent.on_connected = edgeAgent_on_connected
        edge_agent.connect()
        time.sleep(1)
        return edge_agent

    def send_array(self, send_data, device_id, tag_name):
        """
        發送array, 將數據和時間戳打包為一個list發送至dataHUB
        Args:
            send_data (array, m*n*): 發送的資料batch
            device_id (str): 設備ID
            tag_name (str): 發送到那個節點
        """    
        edge_data = EdgeData()
        tag = EdgeTag(device_id, tag_name, send_data.tolist())
        edge_data.tagList.append(tag)



        if(self.edge_agent.sendData(edge_data)):
            log_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(log_time + ' Array Data Send Success!')
            return True
        return False
    
    def send_single(self, send_data, device_id, tag_name):
        """
        發送單一值
        Args:
            send_data (int, str, float): 發送的資料
            device_id (str): 設備ID
            tag_name (str): 發送到那個節點
        """    
        edge_data = EdgeData()
        
        send_value = send_data
        tag = EdgeTag(device_id, tag_name, send_value)
        edge_data.tagList.append(tag)
        
        log_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # rospy.loginfo('Set ' + tag_name + ' as "' + str(send_data[0]) +'" Success!')
        if(self.edge_agent.sendData(edge_data)):
            print(log_time + ' Single Data Send Success!')
            return True
        return False 

    def send_image(self,image_path, device_id, tag_name):
        [timestamp, image_base64] = self.read_img(image_path)
        send_data = numpy.array([timestamp, image_base64.decode('utf-8')])
        return self.send_array(send_data, device_id, tag_name)
        

    def read_img(self,file_path):
        with open(file_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read())
            # encoded_string.decode('utf-8')
        return [datetime.datetime.now().timestamp(), encoded_string]

    def close_connection(self):
        self.edge_agent.disconnect()
        # rospy.loginfo("[SEND] " + self.hyp['node_id'] + " Disconnected.")


hyp = {
    'node_id': 'your_node)id',
    'device_id': {
        'joint': 'joint_device_id',
        'image': 'image__device_id'
    },
    'usr_name': 'your_user_name(email)',
    'password': 'password',
    'edge_type': 'Gateway',
    'connect_type': 'DCCS',
    'api_url': 'https://your_api_url.com',
    'credential_key': 'your_credential_key'
}

datahub_get_ugv_power = datahub_api_get(usr_name=hyp['usr_name'],password=hyp['password'],node_id=hyp['node_id'],
                                   device_id=hyp['device_id'],tag_name="your_tage_name", tag_type=2, array_size=1, mode='your_mode')
print(datahub_get_ugv_power.read_last_data(0))
datahub_get_ugv_power.close_connection()

datahub = datahub_send_data(hyp)
time.sleep(1)
datahub.send_array(numpy.array([1,2,3,4,5]),device_id=hyp['device_id']['image'],tag_name='test_array')
datahub.send_single([0],device_id=hyp['device_id']['image'],tag_name='test_signal')
datahub.send_image("./logo.jpeg",device_id=hyp['device_id']['image'],tag_name='Camera_Test')
datahub.close_connection()