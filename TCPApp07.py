import threading
import subprocess
import os
import time
import datetime
import random
from shutil import copyfile

#def DEBUG_m(dbgString):
#	print 'DEBUG: ' + dbgString

def DEBUG_m(dbgString):
	dbgString = dbgString
	
	
MSG_DELIMITER = '#'

#Client -> Agent
COMM_GET_CAMERA  = 'COMM_GET_CAMERA'
COMM_CAPTURE_IMG = 'COMM_CAPTURE_IMG'
COMM_SEND_FILE_REQ  = 'COMM_SEND_FILE_REQ'
COMM_SEND_FILE_CONF = 'COMM_SEND_FILE_CONF'



AGNT_CONNECT_REQ	= 'AGNT_CONNECT_REQ'
AGNT_HB_REQ		= 'AGNT_HB_REQ'
AGNT_MAKESHOT_REQ	= 'AGNT_MAKESHOT_REQ'
AGNT_SENDFILE_REQ	= 'AGNT_SENDFILE_REQ'

AGNT_SENDFILE_CONF	= 'AGNT_SENDFILE_CONF'
AGNT_MAKESHOT_CONF	= 'AGNT_MAKESHOT_CONF'
AGNT_CONFUSION_IND	= 'AGNT_CONFUSION_IND#'
AGNT_EXPOSING_IND	= 'AGNT_EXPOSING_IND'

AGNT_TRANSFERFILE_IND	= 'AGNT_TRANSFERFILE_IND'
AGNT_CAMSTATE_IND	= 'AGNT_CAMSTATE_IND'

AGNT_DISCONNECT_IND	= 'AGNT_DISCONNECT_IND'

#Agent -> Client
COMM_SEND_FILE_START = 'COMM_SEND_FILE_START'
COMM_SEND_FILE_END   = 'COMM_SEND_FILE_END'

#GPHOTO2 commands to camera
GPH_GET_CAMERA_MODEL = "sudo gphoto2 --get-config=/main/status/cameramodel"
GPH_GET_CAMERA_BATTERY = "sudo gphoto2 --get-config=/main/status/batterylevel"

GPH_RES_ERROR_MARKER = "Error:"
DSLR_PARAM_VALUE_IDX = 2


RES_UNKNOWN_COMM = 'RES_UNKNOWNCOMM'

#Canon ISO values list
#Used to convert ISO value from client application to iso=index for gphoto command
ISOList = ['Auto', '100', '200', '400', '800', '1600', '3200', '6400']


#GPHOTO thread states
SHOOTING_IDLE     = 0
SHOOTING_EXPOSING = 1
SHOOTING_FINISHED = 2

TRANSFERRING_IDLE =3
TRANSFERRING_INPROGRESS = 4
TRANSFERRING_FINISHED = 5

#=================================CLASSES=======================================

class Shot:
	filename = None
	iso      = None
	exposure = None
	
	def __init__(self, isoVal, expVal):
		self.iso = isoVal
		self.exposure = expVal

#===============================================================================

#Parsing configuration values from DSLR
#returned result is a list [ParamName, ParamType, Value]
def ParseDSLRParam(strResult):
	parsedParam = strResult.split('\n')
	return parsedParam

#Return pure param value
def GetParamValue (param):	
	paramValue = param.split(': ')
	return paramValue[1]

#Check that gphoto2 returned error
def IsError(output):
	DEBUG_m( "IsError(), output=" + str(output))
	parsedOutput = output.split()
	DEBUG_m( "IsError(), parsedOutput=" + str(parsedOutput))
	if(([] != parsedOutput) and (parsedOutput[1] == GPH_RES_ERROR_MARKER)):
		return True
	else: return False


#This function returns what camera we are working with
# NONE if no camera
def GetCameraInfo():
	prcss = subprocess.Popen(GPH_GET_CAMERA_MODEL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,  shell=True)
	(output, err) = prcss.communicate()
	prcss_status = prcss.wait()
	if(err != None): return "NONE"
	else : return GetParamValue(ParseDSLRParam(output)[DSLR_PARAM_VALUE_IDX])

def GetCameraBatteryLevel():
	GPH_GET_CAMERA_BATTERY
	prcss = subprocess.Popen(GPH_GET_CAMERA_BATTERY, stdout=subprocess.PIPE, stderr=subprocess.PIPE,  shell=True)
	(output, err) = prcss.communicate()
	prcss_status = prcss.wait()
	if(err != None): return "NONE"
	else : return GetParamValue(ParseDSLRParam(output)[DSLR_PARAM_VALUE_IDX])
	
	
def DUMMY_GetCameraInfo():
	return "DUMMY_CAMERA:#"
	
def DUMMY_ConnectReq():
	return "AGNT_CONNECT_CONF:SUCCESS:DUMMY_CAM#"
	
	
	
	
#Pass a line from Exposing output
#the function detects:
# Camera Status, BulbExposureTime, Saving file
EXPSR_CAM_STATUS = "Camera Status"
EXPSR_BULB_TIME  = "BulbExposureTime"
EXPSR_SAVE_FILE  = "Saving file as"

def ParseExposingOuputLine(line, shotObjToUpdate):
	DEBUG_m("ParseExposingOuputLine ...")
	res = None
	
	#if(IsError(line)) : return "ERROR"
	
	if (EXPSR_CAM_STATUS in line):
		state = line.split(" ")[3]
		res = AGNT_CAMSTATE_IND+":"+state+"#" #parse status value and send
	elif(EXPSR_BULB_TIME in line):
		exposure = line.split(" ")[2]
		res = AGNT_EXPOSING_IND+":"+exposure+"#"#parse time value and send
	elif(EXPSR_SAVE_FILE in line): 
		#parse file name and update the Shot object
		#TBD: Potential problem if this line means start of saving procedure. Need to wait status 0
		fname = line.split(" ")[3]
		fname = fname.split('\n')[0]
		shotObjToUpdate.filename = fname
		
	DEBUG_m("exiting ParseExposingOuputLine")
	return res
	
		
def DUMMY_MakeshotReq2(iso, exposure):
	print "running exposing command ... " + iso + " " + exposure
	
	#Create a Shot object
	CurrentShot = Shot(iso, exposure)
	
	gphotocomm = "sudo gphoto2 --filename=my_bulb_01 --wait-event=2s --set-config iso=" + str(ISOList.index(iso)) + " --set-config eosremoterelease=5 --wait-event=" + exposure +"s --set-config eosremoterelease=4 --wait-event-and-download=5s"
	print gphotocomm
	
	prcss = subprocess.Popen("/home/pi/eos600d_35sec_exposure_script", stdout=subprocess.PIPE, stderr=subprocess.PIPE,  shell=True)
	
	while (prcss.poll() == None):
		line =  prcss.stdout.readline()
		
		print "line = ", line
		result = ParseExposingOuputLine(line, CurrentShot)
		print "parse res = ", result
		if(None != result):
			#TBD: if failed to send over network drop command!
			try:
				#conn.send(result)
				ConnSend(result)
			except:
				prcss.kill()
				break
		
	
	print "Shot object: filename="+CurrentShot.filename + ", iso=" + CurrentShot.iso + ", exposure=" + CurrentShot.exposure
	
	#create temp RAW
	copyfile("testshots/my_bulb_01.cr2", "./"+CurrentShot.filename)
	
	result = "AGNT_MAKESHOT_CONF:SUCCESS:"+CurrentShot.filename+"#"
	return result
	
		#TBD: read output line by line
		# the shooting must go through:
		#	UNKNOWN Camera Status 1
		#	UNKNOWN BulbExposureTime 1 - UNKNOWN BulbExposureTime <exposure>
		#	Saving file as my_bulb_01
		#	UNKNOWN Camera Status 0


	
def Process_MAKESHOT_REQ(iso, exposure):
	global shootingThread
	if (shootingThread == None) or (TRANSFERRING_FINISHED == shootingThread.GetState()):
		shootingThread = GphotoThread(iso, exposure)
		shootingThread.start()
	else:
		#shooting in progress cannot run one more thread
		ConnSend("AGNT_MAKESHOT_CONF:FAILED#")
		

	

class GphotoThread(threading.Thread):
	def __init__(self, iso, exposure):
		super(GphotoThread, self).__init__()
		self.state = SHOOTING_IDLE
		self.iso = iso
		self.exposure = exposure
		
	def run(self):
		#start gphoto
		self.state = SHOOTING_EXPOSING
		#result = GPHOTO2_MakeshotReq(iso, exposure)
		result = DUMMY_MakeshotReq2(self.iso, self.exposure)
		ConnSend(result)
		self.state = SHOOTING_FINISHED
		
	def GetState(self):
		return self.state
		
		

def GPHOTO2_MakeshotReq(iso, exposure):
	print "GPHOTO2_MakeshotReq: running exposing command ... " + iso + " " + exposure
	
	#Create a Shot object
	CurrentShot = Shot(iso, exposure)
	
	# Combine a name for a RAW file to be created by gphoto2
	shotName = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")+"_ISO"+iso+"_EXP"+exposure+".cr2"
	
	#Combine a command for ghoto lib to execute
	gphotocomm = "sudo stdbuf -oL gphoto2 --filename=" + shotName + " --wait-event=2s --set-config iso=" + str(ISOList.index(iso)) + " --set-config eosremoterelease=5 --wait-event=" + exposure +"s --set-config eosremoterelease=4 --wait-event-and-download=5s"

       #prcss = subprocess.Popen(gphotocomm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
	prcss = subprocess.Popen(gphotocomm, 1, stdout=subprocess.PIPE, stderr=None, shell=True)
	
	while (prcss.poll() == None) :
		print "Read one line from stdout ..."
		line =  prcss.stdout.readline()
		DEBUG_m( "line = " + line )
		result = ParseExposingOuputLine(line, CurrentShot)
		print "parse res = ", result
		if(None != result):
			if("ERROR" == result) :
				result = "AGNT_MAKESHOT_CONF:FAILED#"
				return result
			else:
				#conn.send(result)
				ConnSend(result)

		
	print "Check that Shot object is formed ..."
	if(CurrentShot.filename == None):
		print "ERROR: gphoto2 failed to take an image!!!"
		#conn.send("AGNT_MAKESHOT_CONF:FAILED#")
		result = "AGNT_MAKESHOT_CONF:FAILED#"
	else:
		print "Shot object: filename="+CurrentShot.filename + ", iso=" + CurrentShot.iso + ", exposure=" + CurrentShot.exposure
		
		result = "AGNT_MAKESHOT_CONF:SUCCESS:"+CurrentShot.filename+"#"
	
	return result
	
		#TBD: read output line by line
		# the shooting must go through:
		#	UNKNOWN Camera Status 1
		#	UNKNOWN BulbExposureTime 1 - UNKNOWN BulbExposureTime <exposure>
		#	Saving file as my_bulb_01
		#	UNKNOWN Camera Status 0
		

def Process_SENDFILE_REQ(filename):
	#Check if shot is in progress or transferring is in progress
	global shootingThread
	if (shootingThread == None) or (SHOOTING_FINISHED == shootingThread.GetState()):
		shootingThread = TransferingThread(filename)
		shootingThread.start()
	else:
		#shooting or transferring progress cannot run one more thread
		ConnSend(AGNT_SENDFILE_CONF+":"+"SEND_ERR:" +filename+"#")


class TransferingThread(threading.Thread):
	def __init__(self, filename):
		super(TransferingThread, self).__init__()
		self.state = TRANSFERRING_IDLE
		self.filename = filename
		
	def run(self):
		#start transferring
		self.state = TRANSFERRING_INPROGRESS
		DUMMY_StartTransferThread(self.filename)
		self.state = TRANSFERRING_FINISHED
		
	def GetState(self):
		return self.state


def DUMMY_StartTransferThread(filename):
	print "Create Additional Socket for File Transfer"
	TRANSFER_PORT = 5010
	MIN_TRANSFER_PORT = 5010
	MAX_TRANSFER_PORT = 5100
	transPort = random.randint(MIN_TRANSFER_PORT, MAX_TRANSFER_PORT)
	
	transfSkt  = None
	transfConn = None
	transfAddr = None
	try:
		print "Creating transfSkt ..."
		transfSkt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		print "Binding transfSkt ..."
		transfSkt.bind((TCP_IP, transPort))
		print "Listening transfSkt ..."
		transfSkt.listen(1)
	
		#send confirmation that we are waiting for connect
		tmpList = filename.split("/")
		pureFileName = tmpList[len(tmpList)-1]
	
		print "Send confirmation to client that a file is ready to be transferred"
		#conn.send(AGNT_SENDFILE_CONF+":"+"SUCCESS:"+str(os.path.getsize(filename))+":"+pureFileName+":"+str(transPort)+"#")
		ConnSend(AGNT_SENDFILE_CONF+":"+"SUCCESS:"+str(os.path.getsize(filename))+":"+pureFileName+":"+str(transPort)+"#")
	
	except:
		#conn.send(AGNT_SENDFILE_CONF+":"+"SEND_ERR:"+str(os.path.getsize(filename))+":"+pureFileName+"#")
		ConnSend(AGNT_SENDFILE_CONF+":"+"SEND_ERR:"+str(os.path.getsize(filename))+":"+pureFileName+"#")
		print "File Transfer Failed (transfer socket exception)"
		return
	
	print "Wait for Client to connect to Transferring Socket"
	while(None == transfConn):
		transfConn, transfAddr = transfSkt.accept()
	
	print "Client connected ", transfAddr
	
	ThreadSendFile(filename, transfConn)
	transfConn.close()
	transfSkt.close()
	print "Sockets were closed"
	
	os.remove(filename)
	print "File was removed"


# Function to send a file over a network
# The function spawnes a new thread
# In thse scope of this thread a file will be transferred
def ThreadSendFile(filename, connection):
	MAX_BYTES_READ = 4096
	
	result = "SUCCESS"
	filesize = os.path.getsize(filename)
	print "Start sending the file ", filename, filesize, "bytes"
	
	print "Opening the file ", filename
	f = open(filename, "rb")
	print "Read and send ... "
	l = f.read(MAX_BYTES_READ)
	packets = 0
	while (l):
		packets = packets+1
		DEBUG_m('Sending ...' + str(packets))
		connection.send(l)
		l = f.read(MAX_BYTES_READ)

	#TBD: Here we should wait for the confirmation that the client read the file completely?
	f.close()
	print "Done sending"
	




		

	

def ProcessHBReq(probeId):
	return "AGNT_HB_ACK:"+probeId+"#"

#Parses data from socket and forms an array of commands
def RetreiveCommands(data):
	commList = data.split(MSG_DELIMITER)
	commList.remove('')
	return commList



#Command Dispatcher parses commands from client
#and calls appropriate functions
def DispatchCommand(commandStr, scktConn):
	#Strip message from params
	parts = commandStr.split(":")
	msgName = parts[0]
	
	if(COMM_GET_CAMERA == msgName):	return DUMMY_GetCameraInfo() #GetCameraInfo()
	elif(AGNT_CONNECT_REQ == msgName):   return DUMMY_ConnectReq()
	elif(AGNT_MAKESHOT_REQ == msgName):  return Process_MAKESHOT_REQ(parts[1], parts[2])
	elif(AGNT_SENDFILE_REQ == msgName):  return Process_SENDFILE_REQ(parts[1])
	elif(AGNT_HB_REQ == msgName):   return ProcessHBReq(parts[1])
	else : return AGNT_CONFUSION_IND


def IsClosed(dataStr):
	if (dataStr=='') : return True
	else : return False

def DestroyClientConnection():
	#conn.shutdown()
	#conn.close()
	conn.send("genexception")
	#conn = None
	#addr = None

import socket

TCP_IP = ''
TCP_PORT = 5002
BUFF_SIZE = 1024
ClientConnected = False

#TestPartialOutput()

print "Server Started: port=",TCP_PORT

skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
skt.bind((TCP_IP, TCP_PORT))
skt.listen(1)

conn = None
addr = None

ClientConnected = False
connMutex = threading.Lock() # this lock is used in main, shooting and trensferring threads

shootingThread = None

def ConnSend(data):
	with connMutex:
		conn.send(data)
	


while True:
	if ClientConnected == False:
		print 'Waiting Client ...'
		conn, addr = skt.accept()
		ClientConnected = True
		print 'Client connected: ', conn, addr

	else:
		try:
			print "Reading from socket ...", conn
			data = conn.recv(BUFF_SIZE)
			
		except:
			print "Client socket exception. destroy client "
			ClientConnected = False
			pass
			
		#destroy connection if socket was closed
		if(IsClosed(data)):
			print "Client closed the connection"
			ClientConnected = False
			DestroyClientConnection()
			continue
			
		#terminate the server if EXIT command received
		if(data=='EXIT\n'): break
			
			
		print "received data: ", data

		messageList = RetreiveCommands(data)
		print "Messages received: ", messageList
			
		for msg in messageList:
			result = DispatchCommand(msg, conn)
			print "result: ", result
			if(None != result) :
				try:
					#conn.send(result)
					ConnSend(result)
				except:
					print "Client socket exception. destroy client "
					ClientConnected = False
					pass
	
print "Exiting server"
conn.close()
