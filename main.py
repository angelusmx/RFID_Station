from PyQt4 import QtGui, uic, QtCore
import sys
import Queue
import socket
import threading
import RFH630_commands
import time
from time import gmtime, strftime
import logging

# The UI file is in the same folder as the project
qtCreatorFile = "mainwindow_V1.ui"
Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)

# Create a single input and a single output queue for all threads.
data_matrix_q = Queue.Queue()
read_request_q = Queue.Queue()
automatic_queue = Queue.Queue()
manual_queue = Queue.Queue()

# Initial parameters for the logging
logging.basicConfig(filename='RFID_Station_log.log', level=logging.INFO, format='%(asctime)s %(message)s')

# TCP Server that uses individual threads for the different clients
class ThreadedServer(threading.Thread):
    def __init__(self, host, port, auto_q, manual_q, datamatrix_q, read_req_q):
        super(ThreadedServer, self).__init__()
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.s.bind((host, port))
            self.s.listen(2)
            self.auto_q = auto_q
            self.manual_q = manual_q
            self.datamatrix_q = datamatrix_q
            self.read_req_q = read_req_q
            self.stop_request = threading.Event()
            self.clients_count = 0
            self.rfid_client = client_rfid
            self.scanner_client = client_2D_scanner

        except socket.error:
            print 'Failed to create socket'
            sys.exit()
        self.clients = []

    def run(self):
        logging.info('Application Started')
        while not self.stop_request.isSet():
            conn, address = self.s.accept()
            if address[0] == '10.100.25.65':
                self.rfid_client = client_rfid(conn, self.auto_q, self.manual_q, self.datamatrix_q, self.read_req_q)
                self.clients.append(self.rfid_client)
                print '[+] Client connected: {0}'.format(address[0])
                self.clients_count += 1

            if address[0] == '10.100.25.64':
                self.scanner_client = client_2D_scanner(conn, self.auto_q, self.manual_q, self.datamatrix_q, self.read_req_q)
                self.clients.append(self.scanner_client)
                print '[+] Client connected: {0}'.format(address[0])
                self.clients_count += 1

            if self.clients_count == 2:
                print "*** All clients connected ***"
                self.rfid_client.start()
                self.scanner_client.start()

    def join(self, timeout=None):
        self.stop_request.set()
        super(ThreadedServer, self).join(timeout)


class client_rfid(threading.Thread):
    def __init__(self, conn, automatic_q, manual_q, datamatrix_q, read_req_q):
        super(client_rfid, self).__init__()
        self.conn = conn
        self.data = ""
        self.automatic_q = automatic_q
        self.manual_q = manual_q
        self.data_matrix_q = datamatrix_q
        self.read_request_q = read_req_q
        self.tags_list = []

    def run(self):
        # Call the tag writing method only once, the loop is implemented in the PyQt class
        print "the RFID handling service started"
        while True:
            job_inquiry = self.automatic_q.get()
            if job_inquiry == 1:
                self.write_rfid(self.read_request_q, self.data_matrix_q)
            else:
                print "No task request found in the queue"

    def list_tags(self, tag_uid):
        # Check if the numbers of elements is >= 1000

        if len(self.tags_list) >= 1000:
            # Reset the list
            del self.tags_list[:]
            # Insert tag in the list
            self.tags_list.append(tag_uid)
            list_entry_ready = True
            return list_entry_ready

        else:
            self.tags_list.append(tag_uid)
            list_entry_ready = True
            return list_entry_ready

    def check_unique(self, tag_uid):

        # variable to communicate the status of the tag [0] = new [1] =  duplicated
        response = False

        for element in self.tags_list:
            if tag_uid == element:
                print "Duplicated UID, it will be ignored"
                response = False
                continue
            else:
                print "UID is unique to the station"
                response = True
                continue

        return response

    def extract_uid(self, hex_string):
        # This functions takes the UID values and fills with zeros the values under 0xA

        # get the count of present tags
        tags_counter = hex_string[13:17]

        # No tag is present
        if tags_counter == "1 22":
            raw_uid = "No Tag"
        # one Tag is present
        elif tags_counter == "1 0 ":
            raw_uid = hex_string[21:-1]
        else:
            raw_uid = "Error"

        return raw_uid

    def read_rfid(self):

        # Buffer size
        size = 512

        # Send the inventory request
        self.conn.sendall(RFH630_commands.get_UID)

        # expect something in return
        tag_uid = self.conn.recv(size)

        # extract the UID from the response of the device
        complete_UID = RFH630_commands.extract_uid(tag_uid)

        # Read the content of the blocks (from - to of blocks is hard coded)
        print "sending the read command"
        # create the complete command for transmission
        first_block = 0
        final_block = 5

        read_command = RFH630_commands.read_blocks(complete_UID, first_block, final_block)

        self.conn.sendall(read_command)

        # Expect something in return
        tag_content = self.conn.recv(size)

        return complete_UID, tag_content

    def write_rfid(self, read_q, data_m_q):
        size = 512

        # Send the inventory request
        self.conn.sendall(RFH630_commands.get_UID)

        # expect something in return
        tag_uid = self.conn.recv(size)

        # extract the UID from the response of the device
        complete_UID = self.extract_uid(tag_uid)

        # Check the uniqueness of the Tag
        tag_is_unique = self.check_unique(complete_UID)

        # Only one Tag was found in the HF Field
        # TODO: Change the logic to throw a time out
        # TODO: Error handling if no valid scanner Result
        if complete_UID != "No Tag" and tag_is_unique is True:

            print "Tag detected with UID: " + complete_UID
            logging.info("Tag detected with UID: " + complete_UID)
            # Place the read request in the Queue
            read_request = 1
            read_q.put(read_request)

            try:
                # Pull the Data matrix from the Queue
                data_matrix_result = data_m_q.get()
                print "The scanned data is: " + str(data_matrix_result)

                # create the complete command for transmission
                transmission_command = RFH630_commands.write_custom_string(complete_UID, data_matrix_result)
                # write the Memory block n (n as variable)
                self.conn.sendall(transmission_command)

                # check that everything went well
                write_confirmation = self.conn.recv(size)

                if write_confirmation == "\x02sAN WrtMltBlckStr 0\x03":
                    print "*** Writing process returned no errors ****\n"
                    # Enter the tag into the list
                    self.list_tags(complete_UID)
                    # Entry in the log file
                    logging.info("Tag %s written with scanner data %s", complete_UID, data_matrix_result)
                else:
                    print "\n" + "++++ Tag could not be written"

            except data_m_q.empty():
                print "No Scanner value in the Queue"
                self.close()

        else:
            print "No Tag detected, keep waiting"

    def close(self):
        self.conn.close()


class client_2D_scanner(threading.Thread):
    def __init__(self, conn, automatic_q, manual_q, datamatrix_q, read_req_q):
        super(client_2D_scanner, self).__init__()
        self.conn = conn
        self.data = ""
        self.automatic_q = automatic_q
        self.manual_q = manual_q
        self.data_matrix_q = datamatrix_q
        self.read_request_q = read_req_q

    def run(self):
        pass

    def read(self):
        size = 512
        try:
            self.conn.sendall("\x02read\x03")
            data_matrix = self.conn.recv(size)
        except data_matrix == "NoRead":
            print "Not possible to read Data from the label"
        finally:
            return data_matrix

    def close(self):
        self.conn.close()


class MyApp(QtGui.QMainWindow, Ui_MainWindow):
    def __init__(self, automatic_queue, manual_queue, data_matrix_q, read_request_q, client_rfid, client_reader):
        QtGui.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)

        # The client objects
        self.client_rfid = client_rfid
        self.client_reader = client_reader

        # Define the callback functions of the automatic functions
        self.btn_auto_start.clicked.connect(self.auto_start)
        self.btn_auto_stop.clicked.connect(self.auto_stop)

        # Define the callback functions of the manual functions
        self.btn_man_datamatrix.clicked.connect(self.man_datamatrix)
        self.btn_man_rfid.clicked.connect(self.man_rfid)
        self.speed_slider.valueChanged.connect(self.slider_valuechange)
        self.port_num = 2113
        self.automatic_trigger = False
        self.automatic_queue = automatic_queue
        self.manual_queue = manual_queue
        self.data_matrix_q = data_matrix_q
        self.read_request_q = read_request_q

    def slider_valuechange(self):
        value = self.speed_slider.value()
        self.txt_speed.setText(str(value))

    def console_output(self, input_text):
        # Write text to the console
        current_time = strftime("%H:%M:%S", gmtime())
        self.txt_console.append(input_text + "-" + current_time)

    def auto_start(self):
        self.automatic_trigger = True
        self.btn_auto_start.setEnabled(False)
        self.btn_status_run.setStyleSheet("background-color: green")
        self.btn_status_idle.setStyleSheet("background-color: None")
        self.console_output("Automatisches Prozess gestarted")
        self.automatic_loop()

    def auto_stop(self):
        self.automatic_trigger = False
        self.btn_auto_start.setEnabled(True)
        self.btn_status_run.setStyleSheet("background-color: None")
        self.btn_status_idle.setStyleSheet("background-color: yellow")
        self.console_output("Automatisches Prozess wurde angehalten")
        # QtGui.QApplication.processEvents()

    def man_datamatrix(self):
        self.console_output("Information auf die Datamatrix wird ausgelesen")
        datamatrix = self.client_reader.read()
        lot_number = datamatrix[0:10]
        year_of_man = datamatrix[10:14]
        month_of_man = datamatrix[15:16]
        dom_complete = str(year_of_man) + "-" + str(month_of_man)
        counter_num = datamatrix[16:21]

        self.txt_lot.setText(lot_number)
        self.txt_counter.setText(counter_num)
        self.txt_dom.setText(dom_complete)

    def man_rfid(self):
        self.console_output("Transponder Information wird ausgelesen")
        rfid_uid, rfid_data = self.client_rfid.read_rfid()
        self.txt_uid.setText(rfid_uid)
        self.txt_data.setText(rfid_data)
        logging.info("Manual reading of RFID Tag: [UID] %s, [Data] %s", rfid_uid, rfid_data)

    def automatic_loop(self):
        while self.automatic_trigger:
            QtCore.QCoreApplication.processEvents()
            self.automatic_queue.put(1)
            time.sleep(1)


# ************** Start the server **************

port_num = 2113


#while tcp_server.clients_count != 2:
 #   continue

app = QtGui.QApplication(sys.argv)

# Instantiate the server class and start listening for clients
tcp_server = ThreadedServer('', port_num, automatic_queue, manual_queue, data_matrix_q, read_request_q)
tcp_server.start()

wx = QtGui.QDialog()
wx.setWindowModality(True)
wx.show()

iii = 0

while iii != 10:
    QtGui.QApplication.processEvents()
    iii+=1
    time.sleep(0.5)
    QtGui.QApplication.processEvents()

wx.close()


w = MyApp(automatic_queue, manual_queue, data_matrix_q, read_request_q, tcp_server.rfid_client, tcp_server.scanner_client)

w.setWindowTitle('RFID Labels Station V1.0')
w.show()
logging.info('Main PyQt window started')

# Set the color of the idle button
w.btn_status_idle.setStyleSheet("background-color: yellow")

sys.exit(app.exec_())
