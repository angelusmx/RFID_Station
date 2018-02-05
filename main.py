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
status_queue = Queue.Queue()

# Initial parameters for the logging
logging.basicConfig(filename='RFID_Station_log.log', level=logging.INFO, format='%(asctime)s %(message)s')


# TCP Server that uses individual threads for the different clients
class ThreadedServer(threading.Thread):
    def __init__(self, host, port, auto_q, manual_q, datamatrix_q, read_req_q, comms_q, status_q):
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
            self.status_q = status_q
            self.stop_request = threading.Event()
            self.clients_count = 0
            self.rfid_client = ClientRFID
            self.scanner_client = ClientScanner
            self.auto_trigger = False

        # TODO: Place the right error after the socket
        except socket.error:
            # Log to file and output to console
            info_error_socket = 'Failed to create socket'
            self.comms_q.put(info_error_socket)
            logging.info(info_error_socket)

            sys.exit()
        self.clients = []

    def run(self):
        logging.info('Application Started')
        self.auto_trigger = False
        while not self.stop_request.isSet():
            conn, address = self.s.accept()
            if address[0] == '10.100.25.65':
                self.rfid_client = ClientRFID(conn, self.auto_q, self.manual_q, self.datamatrix_q, self.read_req_q,
                                               self.comms_q, self.status_q)
                self.clients.append(self.rfid_client)
                info_rfid_connected = '[+] Client connected: {0}'.format(address[0])
                print info_rfid_connected
                # Entry in log und output to console
                logging.info(info_rfid_connected)
                self.comms_q.put(info_rfid_connected)
                self.clients_count += 1

            if address[0] == '10.100.25.64':
                self.scanner_client = ClientScanner(conn, self.auto_q, self.manual_q, self.datamatrix_q,
                                                        self.read_req_q, self.comms_q)
                self.clients.append(self.scanner_client)
                info_scanner_connected = '[+] Client connected: {0}'.format(address[0])
                print info_scanner_connected
                # Entry in log und output to console
                logging.info(info_scanner_connected)
                self.comms_q.put(info_scanner_connected)
                self.clients_count += 1

            if self.clients_count == 2:
                self.rfid_client.start()
                self.scanner_client.start()
                # Enter in log and output to console
                info_all_connected = " ** All clients connected **"
                logging.info(info_all_connected)
                self.comms_q.put(info_all_connected)

    def join(self, timeout=None):
        self.stop_request.set()
        super(ThreadedServer, self).join(timeout)


class ClientRFID(threading.Thread):
    def __init__(self, conn, automatic_q, manual_q, datamatrix_q, read_req_q, comms_q, status_q):
        super(ClientRFID, self).__init__()
        self.conn = conn
        self.data = ""
        self.automatic_q = automatic_q
        self.manual_q = manual_q
        self.data_matrix_q = datamatrix_q
        self.read_request_q = read_req_q
        self.comms_q = comms_q
        self.status_q = status_q
        self.tags_list = []
        self.stop_request = threading.Event()
        self.auto_loop = False

    def run(self):
        # Call the tag writing method only once, the loop is implemented in the PyQt class
        print "the RFID handling service started"
        while not self.stop_request.isSet():
            while self.auto_loop:
                self.write_rfid(self.read_request_q, self.data_matrix_q)

    def join(self, timeout=2):
        self.stop_request.set()
        super(ClientRFID, self).join(2)

    def loop_control(self):
        if self.auto_loop:
            self.auto_loop = False
        else:
            self.auto_loop = True

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

        if not self.tags_list:  # Pythonic way of checking if the list is empty
            response = True
            return response
        else:
            for element in self.tags_list:
                if tag_uid == element:
                    print "Duplicated UID, it will be ignored"
                    response = False
                    break
                else:
                    print "UID is unique to the station"
                    response = True
                    continue

        return response

    def read_rfid(self):

        # Buffer size
        size = 512

        # Get the UID automatically from the device
        self.conn.sendall(RFH630_commands.get_UID_auto)
        # expect something in return
        tag_uid = self.conn.recv(size)

        # extract the UID from the response of the device
        raw_uid, pretty_uid, spaces_uid = RFH630_commands.extract_uid(tag_uid)

        # Read the content of the blocks (from - to of blocks is hard coded)

        # create the complete command for transmission
        first_block = 0
        final_block = 5

        read_command = RFH630_commands.read_blocks(spaces_uid, first_block, final_block)

        self.conn.sendall(read_command)

        # Expect something in return
        tag_content = self.conn.recv(size)
        tag_content = tag_content[22:]

        return pretty_uid, tag_content

    def write_rfid(self, read_q, data_m_q):
        size = 512

        # Get the UID automatically from the device
        self.conn.sendall(RFH630_commands.get_UID_auto)
        # expect something in return
        self.conn.settimeout(1)
        try:
            tag_uid = self.conn.recv(size)
        except socket.timeout:
            print "no data seen in " + str(1) + " seconds, trying later"
            return
        else:
            # extract the UID from the response of the device
            raw_uid, pretty_uid, spaces_uid = RFH630_commands.extract_uid(tag_uid)

            # Check the uniqueness of the Tag
            # tag_is_unique = self.check_unique(complete_UID)
            tag_is_unique = True

            # Only one Tag was found in the HF Field
            # TODO: Rework the delay logic, the pause is not between the insertion in the queue but the reading of the tag
            # TODO: Error handling if no valid scanner Result

            # Log the event and write to the console
            info_tag_detected = "Tag detected with UID: " + pretty_uid
            self.comms_q.put(info_tag_detected)
            logging.info("Tag detected with UID: " + pretty_uid)

            # Place the read request in the Queue
            read_request = 1
            read_q.put(read_request)
            # The task is done
            read_q.task_done()

            # Pull the Data matrix from the Queue
            data_matrix_result = data_m_q.get()

            # Check the content of the scanned data
            if data_matrix_result == "NoRead":
                # Read 2D Error
                error_code = "Keine datamatrix"
                self.status_q.put(error_code)
                return error_code

            else: # Some code was read

                # create the complete command for transmission
                transmission_command = RFH630_commands.write_custom_string(spaces_uid, data_matrix_result)
                # write the Memory block n (n as variable)
                self.conn.sendall(transmission_command)

                # check that everything went well
                write_confirmation = self.conn.recv(size)

                if write_confirmation == "\x02sAN WrtMltBlckStr 0\x03":
                    print "*** Writing process IO for Tag ++++ " + str(pretty_uid) + "++++"
                    # Enter the tag into the list
                    self.list_tags(raw_uid)
                    # Entry in log and output to console
                    info_write_success = "Tag " + str(raw_uid) + " written with scanner data " \
                                                + str(data_matrix_result) + "\n"
                    logging.info(info_write_success)
                    self.comms_q.put(info_write_success)

                    # Write the status of the variable
                    error_code = "process completed"
                    self.status_q.put(error_code)
                    return error_code

                else:
                    print "\n" + "++++ Tag " + str(pretty_uid) + " could not be written"

                    # Write the status of the variable
                    error_code = "Writing failed"
                    self.status_q.put(error_code)
                    return error_code

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
        # print "the 2D Scanner handling service started"
        while not self.stop_request.isSet():
            try:
                self.read_request_q.get(False)
            except Queue.Empty:
                # Handle empty queue here
                pass
            else:
                # Handle task here and call q.task_done()
                self.conn.sendall("\x02read\x03")
                data_matrix = self.conn.recv(self.buffer_size)

                # Place the value in the values queue
                self.data_matrix_q.put(data_matrix)
                #self.read_request_q.task_done()

    def join(self, timeout=None):
        self.stop_request.set()
        super(ClientScanner, self).join(timeout)

    def read(self):
        size = 512
        self.conn.sendall("\x02read\x03")
        data_matrix = self.conn.recv(size)
        if data_matrix != "NoRead":
            self.comms_q.put(data_matrix)
            return data_matrix
        else:
            info_no_datamatrix = "No Datamatrix could be read"
            # Entry in Log und output to console
            self.comms_q.put(info_no_datamatrix)
            logging.info(info_no_datamatrix)
            return data_matrix

    def close(self):
        self.conn.close()


class MyApp(QtGui.QMainWindow, Ui_MainWindow):
    def __init__(self, automatic_queue, manual_queue, data_matrix_q, read_request_q, client_rfid, client_reader, comms_q, status_q):
        QtGui.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)

        # The delay for the slider
        self.delay_time = 500
        self.timeoutTimer = QtCore.QTimer()
        self.timeoutTimer.setInterval(self.delay_time)  # The time on the slider in s
        self.timeoutTimer.setSingleShot(False)
        self.timeoutTimer.timeout.connect(self.recursive_timer)

        # The recursive timer for the message queue
        self.pull_frequency = 500
        self.refresh_timer = QtCore.QTimer()
        self.refresh_timer.setInterval(self.pull_frequency)
        self.refresh_timer.setSingleShot(False)
        self.refresh_timer.timeout.connect(self.pull_messages)

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
        self.comms_q = comms_q
        self.status_q = status_q

    def recursive_timer(self):
        # Executes this code every n seconds (as given by the slider)
        operation_result = self.status_q.get()

        if operation_result != "process completed":
            # Stop the automatic process
            print "I stopped because of an error: " + operation_result
            self.auto_stop()

        else:
            # Place a new job request for the RFID transponder in the queue
            self.automatic_queue.put(1)

    def pull_messages(self):
        # Pulls messages from the message queue and forwards them to the console of the GUI
        while not self.comms_q.empty():
            # Forward to the console
            message = self.comms_q.get()
            self.console_output(message)
        else:
            pass

    def closeEvent(self, event):
        # Entry in logfile
        logging.info('Application terminated')
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
        # pass

    def console_output(self, input_text):
        # Write text to the console
        current_time = strftime("%H:%M:%S", gmtime())
        self.txt_console.append(input_text + "-" + current_time)
        self.txt_console.append("\n")

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
        self.btn_auto_stop.setStyleSheet("background-color: Red")
        self.btn_auto_start.setStyleSheet("background-color: None")
        self.console_output("Automatisches Prozess gestarted")
        # Give the RFID worker the first job, the rest ones are given sequentially by the recursive timer
        self.client_rfid.loop_control()
        #self.automatic_loop()

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
        self.btn_auto_stop.setStyleSheet("background-color: None")
        self.btn_auto_start.setStyleSheet("background-color: Green")
        self.console_output("Automatisches Prozess wurde angehalten")
        # QtGui.QApplication.processEvents()

        self.client_rfid.loop_control()

    def man_datamatrix(self):
        self.console_output("Information auf die Datamatrix wird ausgelesen")
        datamatrix = self.client_reader.read()
        if datamatrix!= "NoRead":
            lot_number = datamatrix[0:10]
            year_of_man = datamatrix[10:12]
            month_of_man = datamatrix[12:14]
            day_of_man = datamatrix[14:16]
            dom_complete = "20" + str(year_of_man) + "-" + str(month_of_man) + "-" + str(day_of_man)
            counter_num = datamatrix[16:21]
        else:
            lot_number = "Keine Daten"
            dom_complete = "Keine Daten"
            counter_num = "Keine Daten"

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
                self.timeoutTimer.start()

        else:
            self.automatic_queue.queue.clear()
            self.timeoutTimer.stop()


# ************** Start the server **************

# Port number for the TCP Server
port_num = 2113
app = QtGui.QApplication(sys.argv)
# Instantiate the server class and start listening for clients
tcp_server = ThreadedServer('', port_num, automatic_queue, manual_queue, data_matrix_q, read_request_q, comms_queue, status_queue)
tcp_server.start()

while tcp_server.clients_count != 2:
    continue

w = MyApp(automatic_queue, manual_queue, data_matrix_q, read_request_q, tcp_server.rfid_client, tcp_server.scanner_client, comms_queue, status_queue)

w.setWindowTitle('RFID Labels Station V1.0')
w.show()
logging.info('Main PyQt window started')

# Start the recursive pull for the console messages
w.refresh_timer.start()

# Set the color of the idle button and the auto start
w.btn_status_idle.setStyleSheet("background-color: yellow")
w.btn_auto_start.setStyleSheet("background-color: Green")

sys.exit(app.exec_())
