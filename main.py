from PyQt4 import QtGui, uic, QtCore
import sys
import Queue
import socket
import threading
import RFH630_commands
from time import gmtime, strftime
import logging

# The UI file is in the same folder as the project
qtCreatorFile = "mainwindow_V4.ui"
Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)

# Create a single input and a single output queue for all threads.
data_matrix_q = Queue.Queue()
read_request_q = Queue.Queue()
automatic_queue = Queue.Queue()
manual_queue = Queue.Queue()
comms_queue = Queue.Queue()

# Initial parameters for the logging
logging.basicConfig(filename='RFID_Station_log.log', level=logging.INFO, format='%(asctime)s %(message)s')


# TCP Server that uses individual threads for the different clients
class ThreadedServer(threading.Thread):
    def __init__(self, host, port, auto_q, manual_q, datamatrix_q, read_req_q, comms_q):
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
            self.comms_q = comms_q
            self.stop_request = threading.Event()
            self.clients_count = 0
            self.rfid_client = ClientRFID
            self.scanner_client = ClientScanner
            self.auto_trigger = False

        # TODO: Place the right error after the socket
        except socket.error:
            print 'Failed to create socket'
            sys.exit()
        self.clients = []

    def run(self):
        logging.info('Application Started')
        self.auto_trigger = False
        while not self.stop_request.isSet():
            conn, address = self.s.accept()
            if address[0] == '10.100.25.65':
                self.rfid_client = ClientRFID(conn, self.auto_q, self.manual_q, self.datamatrix_q, self.read_req_q,
                                               self.comms_q)
                self.clients.append(self.rfid_client)
                print '[+] Client connected: {0}'.format(address[0])
                self.clients_count += 1

            if address[0] == '10.100.25.64':
                self.scanner_client = ClientScanner(conn, self.auto_q, self.manual_q, self.datamatrix_q,
                                                        self.read_req_q, self.comms_q)
                self.clients.append(self.scanner_client)
                print '[+] Client connected: {0}'.format(address[0])
                self.clients_count += 1

            if self.clients_count == 2:
                self.rfid_client.start()
                self.scanner_client.start()
                print "*** All clients connected ***"

    def join(self, timeout=None):
        self.stop_request.set()
        super(ThreadedServer, self).join(timeout)


class ClientRFID(threading.Thread):
    def __init__(self, conn, automatic_q, manual_q, datamatrix_q, read_req_q, comms_q):
        super(ClientRFID, self).__init__()
        self.conn = conn
        self.data = ""
        self.automatic_q = automatic_q
        self.manual_q = manual_q
        self.data_matrix_q = datamatrix_q
        self.read_request_q = read_req_q
        self.comms_q = comms_q
        self.tags_list = []
        self.stop_request = threading.Event()

    def run(self):
        # Call the tag writing method only once, the loop is implemented in the PyQt class
        print "the RFID handling service started"
        while not self.stop_request.isSet():
            job_enquiry = self.automatic_q.get()
            if job_enquiry == 1:
                self.write_rfid(self.read_request_q, self.data_matrix_q)
            else:
                print "No task request found in the queue"

    def join(self, timeout=2):
        self.stop_request.set()
        super(ClientRFID, self).join(2)

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

        if self.tags_list.__len__() == 0:
            response = True
            return response

        else:

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
        # tag_is_unique = self.check_unique(complete_UID)
        tag_is_unique = True

        # Only one Tag was found in the HF Field
        # TODO: Change the logic to throw a time out
        # TODO: Error handling if no valid scanner Result
        if complete_UID != "No Tag" and tag_is_unique:

            # Log the event and write to the console
            info_tag_detected = "Tag detected with UID: " + complete_UID
            self.comms_q.put(info_tag_detected)
            logging.info("Tag detected with UID: " + complete_UID)

            # Place the read request in the Queue
            read_request = 1
            read_q.put(read_request)

            try:
                # Pull the Data matrix from the Queue
                data_matrix_result = data_m_q.get()
                info_scanned_data = "The scanned data is: " + str(data_matrix_result)
                # Output event to console
                self.comms_q.put(info_scanned_data)

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
                    # Entry in log and output to console
                    info_write_success = "Tag %s written with scanner data %s " + str(complete_UID) + " " + str(data_matrix_result)
                    logging.info(info_write_success)
                    self.comms_q.put(info_write_success)
                else:
                    print "\n" + "++++ Tag could not be written"

            except data_m_q.empty():
                print "No Scanner value in the Queue"
                self.close()

        else:
            print "No Tag detected, keep waiting"

    def close(self):
        self.conn.close()


class ClientScanner(threading.Thread):
    def __init__(self, conn, automatic_q, manual_q, datamatrix_q, read_req_q, comms_q):
        super(ClientScanner, self).__init__()
        self.conn = conn
        self.data = ""
        self.automatic_q = automatic_q
        self.manual_q = manual_q
        self.data_matrix_q = datamatrix_q
        self.read_request_q = read_req_q
        self.comms_q = comms_q
        self.stop_request = threading.Event()
        self.buffer_size = 512

    def run(self):
        print "the 2D Scanner handling service started"
        while not self.stop_request.isSet():
            try:
                self.read_request_q.get()
                self.conn.sendall("\x02read\x03")
                data_matrix = self.conn.recv(self.buffer_size)
                # Place the value in the values queue
                self.data_matrix_q.put(data_matrix)
            except self.read_request_q.Empty:
                continue

    def join(self, timeout=None):
        self.stop_request.set()
        super(ClientScanner, self).join(timeout)

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

        # The delay for the slider
        self.delay_time = 1000
        self.timeoutTimer = QtCore.QTimer()
        self.timeoutTimer.setInterval(self.delay_time)  # The time on the slider in s
        self.timeoutTimer.setSingleShot(False)
        self.timeoutTimer.timeout.connect(self.recursive_timer)

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
        self.automatic_trigger = False
        self.automatic_queue = automatic_queue
        self.manual_queue = manual_queue
        self.data_matrix_q = data_matrix_q
        self.read_request_q = read_request_q

    def recursive_timer(self):
        # Executes this code every n seconds (as given by the slider)
        self.automatic_queue.put(1)

    def closeEvent(self, event):
        # Terminate the communications to clients
        self.client_rfid.close()
        self.client_reader.close()
        # Close all the threads
        for tr in threading.enumerate():
            if tr.isAlive():
                tr._Thread__stop()
        # and afterwards call the closeEvent of the super-class
        super(QtGui.QMainWindow, self).closeEvent(event)

    def slider_valuechange(self):
        self.delay_time = self.speed_slider.value() * 1000
        print self.delay_time

    def console_output(self, input_text):
        # Write text to the console
        current_time = strftime("%H:%M:%S", gmtime())
        self.txt_console.append(input_text + "-" + current_time)

    def auto_start(self):
        self.automatic_trigger = True
        # Change the status of the buttons
        self.btn_auto_start.setEnabled(False)
        self.speed_slider.setEnabled(False)
        self.btn_man_datamatrix.setEnabled(False)
        self.btn_man_rfid.setEnabled(False)

        self.timeoutTimer.setInterval(self.delay_time)

        # Change the colors of the status buttons
        self.btn_status_run.setStyleSheet("background-color: green")
        self.btn_status_idle.setStyleSheet("background-color: None")
        self.console_output("Automatisches Prozess gestarted")
        self.automatic_loop()

    def auto_stop(self):
        self.automatic_trigger = False
        self.automatic_loop()
        # Change the status of the buttons
        self.btn_auto_start.setEnabled(True)
        self.speed_slider.setEnabled(True)
        self.btn_man_datamatrix.setEnabled(True)
        self.btn_man_rfid.setEnabled(True)
        # Change the colors of the buttons
        self.btn_status_run.setStyleSheet("background-color: None")
        self.btn_status_idle.setStyleSheet("background-color: yellow")
        self.console_output("Automatisches Prozess wurde angehalten")
        # QtGui.QApplication.processEvents()

    def man_datamatrix(self):
        self.console_output("Information auf die Datamatrix wird ausgelesen")
        datamatrix = self.client_reader.read()
        lot_number = datamatrix[0:10]
        year_of_man = datamatrix[10:12]
        month_of_man = datamatrix[12:14]
        day_of_man = datamatrix[14:16]
        dom_complete = "20" + str(year_of_man) + "-" + str(month_of_man) + "-" + str(day_of_man)
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
        if self.automatic_trigger:
            lots_of_jobs = 1000
            for i in range(1, lots_of_jobs, 1):
                #self.automatic_queue.put(1)
                #QtCore.QCoreApplication.processEvents()
                self.timeoutTimer.start()

        else:
            self.automatic_queue.queue.clear()
            self.timeoutTimer.stop()


# ************** Start the server **************

# Port number for the TCP Server
port_num = 2113
app = QtGui.QApplication(sys.argv)
# Instantiate the server class and start listening for clients
tcp_server = ThreadedServer('', port_num, automatic_queue, manual_queue, data_matrix_q, read_request_q)
tcp_server.start()

while tcp_server.clients_count != 2:
    continue

w = MyApp(automatic_queue, manual_queue, data_matrix_q, read_request_q, tcp_server.rfid_client, tcp_server.scanner_client)

w.setWindowTitle('RFID Labels Station V1.0')
w.show()
logging.info('Main PyQt window started')

# Set the color of the idle button
w.btn_status_idle.setStyleSheet("background-color: yellow")

sys.exit(app.exec_())
