# Writing Station for RFID HF Labels

The application transports the information printed on a 2D Datamatrix into a HF-RFID Transponder, the datamatrix and the transponder constitute a single unit (a label). The labels are delivered in a roll, there are 3 different formats, the station can be mechanically adjusted to accomodate the three diferent formats. The formats are for the software irrelevant.

### Prerequisites

The application requires the following libraries to run

```
PyQt4
Queue
socket
threading
```

### GUI

The GUI was designed using Qt Creator, alternatively the .xml file that resuls can be edited manually. The resolution of the screen was limited to 800 x480 px 

## Running the application

The program is mainly divided in two files:

```
main.py
RFH630_commands.py

```
To execute the program, `the main.py` file needs to be executed, the content of the second file are command and service routines used for interacting with the RFID transponder, the above mentioned libraries are of course the basic requierment for running the application

## Deployment

The deployment of the application was concieved from the beginning to be deployed on the Raspberry Pi V2. The reason for the choice is mainly that the Raspberry offers a passing touch screen that merges seamlessly with the small embedded PC, in other words a formal PC is not required for running the application and the control interface. Since the application does not demand many resources from the host system the Raspberry was the ideal choice. The host system used had the following characteristics:

* Raspbian Jeesie

## Built With

* [Pycharm] (https://www.jetbrains.com/pycharm/)
* [PyQt](https://wiki.python.org/moin/PyQt) - Python bindings for the Qt cross-platform GUI/XML/SQL C++ framework

## Contributing

Please read [CONTRIBUTING.md](https://gist.github.com/PurpleBooth/b24679402957c63ec426) for details on our code of conduct, and the process for submitting pull requests to me.

## Versioning

Used was [Github](https://github.com/) for versioning and management. For the versions available, see the [tags on this repository](https://github.com/angelusmx/RFID_Station/). 

## Author

* **Angel Canizales**

See also the list of [contributors](https://github.com/your/project/contributors) who participated in this project.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* My colleages from Qiagen from the Software development for their ideas and open mind to discussion
* The Stack overflow community with their always precious suggestions to all issues possible
