#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace openplc {

struct RuntimeCycleResult
{
    std::vector<uint8_t> tx;
    std::vector<uint8_t> rx;
    bool comm_disconnected = false;
    bool comm_error = false;
    bool checksum_error = false;
    std::string error_text;
};

class ProtocolDslRuntime
{
public:
    RuntimeCycleResult runCycleTcp(const std::vector<uint8_t>& tx,
                                   const std::string& host,
                                   uint16_t port,
                                   int timeout_ms,
                                   bool verify_crc16 = true) const;

    RuntimeCycleResult runCycleRtu(const std::vector<uint8_t>& tx,
                                   const std::string& serial_port,
                                   int baud,
                                   char parity,
                                   int data_bits,
                                   int stop_bits,
                                   int timeout_ms,
                                   bool verify_crc16 = true) const;

    static bool verifyCrc16Modbus(const std::vector<uint8_t>& frame);
};

} // namespace openplc
