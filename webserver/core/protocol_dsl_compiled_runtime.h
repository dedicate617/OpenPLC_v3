#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace openplc {

struct CompiledToken
{
    std::string op;        // byte/ascii/field/checksum/term
    std::string field;
    std::string type;
    std::string algo;
    std::string text;
    uint8_t byte_value = 0;
};

struct CompiledSession
{
    std::string session_name;
    std::vector<CompiledToken> tx_ir;
    std::vector<CompiledToken> rx_ir;
};

uint16_t crc16_modbus(const uint8_t* data, size_t len);
uint8_t xor8(const uint8_t* data, size_t len);
uint8_t sum8(const uint8_t* data, size_t len);

std::vector<uint8_t> append_checksum(const std::vector<uint8_t>& payload, const std::string& algo);

} // namespace openplc
