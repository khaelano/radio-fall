# Radio configuration

`receivers.json` is the versioned physical inventory. It must be populated
with the actual MAC addresses and placements discovered from the boards before
collecting data. Selectable on-air settings live in `profiles/`; provisioning
one profile writes it to every connected board's NVS before collection.

The repository profiles use the Indonesia (`ID`) regulatory domain, 20 MHz
bandwidth, and a fixed 100 Hz sensing rate. The 5 GHz profile intentionally
uses a non-DFS channel. A 5 GHz session requires ESP32-C5 for the transmitter
and every receiver; 2.4 GHz sessions may mix ESP32-C5 and ESP32-C6 boards.

Connect receivers through a powered USB hub with one native USB Serial/JTAG
link per board. `/dev/ttyACM*` names are intentionally not stored here: the
collector binds each link by the firmware-reported MAC and stable device ID.
