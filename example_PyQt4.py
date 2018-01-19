from PyQt4 import QtGui, uic, QtCore
import sys
import Queue
import socket
import threading
import RFH630_commands
import time
from time import gmtime, strftime
from guiLoop import guiLoop # https://gist.github.com/niccokunzmann/8673951

# The UI file is in the same folder as the project
qtCreatorFile = "mainwindow_V1.ui"

Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)

# Create a single input and a single output queue for all threads.
data_matrix_q = Queue.Queue()
read_request_q = Queue.Queue()
automatic_queue = Queue.Queue()
manual_queue = Queue.Queue()

@guiLoop
def led_blink(argument):
    while 1:
        if argument == "start":
            yield 0.5  # time to wait


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

        except socket.error:
            print 'Failed to create socket'
            sys.exit()
        self.clients = []

    def run(self):
        clients_connected = 0
        print "program started"
        while not self.stop_request.isSet():
            conn, address = self.s.accept()
            if address[0] == '10.100.25.65':
                rfid = client_rfid(conn, self.auto_q, self.manual_q, self.datamatrix_q, self.read_req_q)
                self.clients.append(rfid)
                print '[+] Client connected: {0}'.format(address[0])
                print self.clients
                self.clients_count += 1

            if address[0] == '10.100.25.64':
                scanner = client_2D_scanner(conn, self.auto_q, self.manual_q, self.datamatrix_q, self.read_req_q)
                self.clients.append(scanner)
                print '[+] Client connected: {0}'.format(address[0])
                print self.clients
                self.clients_count += 1

            if self.clients_count == 2:
                print "*** All clients connected ***"
                rfid.start()
                scanner.start()
                return self.clients_count, self.clients

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

    def run(self):
        # Call the tag writing method only once, the loop is implemented in the PyQt class
        print "the RFID handling service started"
        while True:
            job_inquiry = self.automatic_q.get()
            if job_inquiry == 1:
                self.write_rfid(self.read_request_q, self.data_matrix_q)
            else:
                print "No task request found in the queue"

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

    def write_rfid(self, read_q, data_m_q):
        size = 512

        the_test = RFH630_commands.get_UID

        # Send the inventory request
        self.conn.sendall(RFH630_commands.get_UID)

        # expect something in return
        tag_uid = self.conn.recv(size)

        # extract the UID from the response of the device
        complete_UID = self.extract_uid(tag_uid)

        # Only one Tag was found in the HF Field
        # TODO: Change the logic to throw a time out
        # TODO: Error handling if no valid scanner Result
        if complete_UID != "No Tag":

            print "Tag detected with UID: " + complete_UID
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
                    # TODO: Input the processed information (UID and content into the DB)
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
        # Call the tag writing method only once, the loop is implemented in the PyQt class
        print "the 2D Scanner process started"
        while True:
            job_inquiry = self.read_request_q.get()
            if job_inquiry == 1:
                self.get_data_matrix(self.data_matrix_q)
            else:
                print "No task request found in the queue"

    def get_data_matrix(self, data_m_q):
        size = 512
        try:
            self.conn.sendall("\x02read\x03")
            data_matrix = self.conn.recv(size)
            # Place the value in the values queue
            data_m_q.put(data_matrix)
        # TODO: Exception to the reading process
        except "No read":
            print "Not possible to read Data from the label"

    def close(self):
        self.conn.close()


class MyApp(QtGui.QMainWindow, Ui_MainWindow):
    def __init__(self, automatic_queue, manual_queue, data_matrix_q, read_request_q):
        QtGui.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)

        # Define the callback functions of the automatic functions
        self.btn_auto_start.clicked.connect(self.auto_start)
        self.btn_auto_stop.clicked.connect(self.auto_stop)

        # Define the callback functions of the manual functions
        self.btn_man_datamatrix.clicked.connect(self.man_datamatrix)
        self.btn_man_rfid.clicked.connect(self.man_rfid)
        self.port_num = 2113
        self.automatic_trigger = False
        self.automatic_queue = automatic_queue
        self.manual_queue = manual_queue
        self.data_matrix_q = data_matrix_q
        self.read_request_q = read_request_q

        # Start the TCP/IP Server
        get_conns = ThreadedServer('', self.port_num, self.automatic_queue, self.manual_queue, self.data_matrix_q, self.read_request_q)
        get_conns.start()

        while get_conns.clients_count != 2:
            # block the start button until the clients are connected
            self.btn_auto_start.setEnabled(False)
            self.btn_auto_stop.setEnabled(False)

        # Release the auto start button for operation
        self.btn_auto_start.setEnabled(True)
        self.btn_auto_stop.setEnabled(True)
        get_conns.join()

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
        #QtGui.QApplication.processEvents()

    def man_datamatrix(self):
        self.console_output("Information auf die Datamatrix wird ausgelesen")

    def man_rfid(self):
        self.console_output("Transponder Information wird ausgelesen")

    def automatic_loop(self):
        while self.automatic_trigger:
            QtCore.QCoreApplication.processEvents()
            self.automatic_queue.put(1)
            time.sleep(1)

app = QtGui.QApplication(sys.argv)
w = MyApp(automatic_queue, manual_queue, data_matrix_q, read_request_q)

w.setWindowTitle('RFID Labels V1.0')
w.show()

# Set the color of the idle button
w.btn_status_idle.setStyleSheet("background-color: yellow")

led_blink(w, 'start')

sys.exit(app.exec_())
