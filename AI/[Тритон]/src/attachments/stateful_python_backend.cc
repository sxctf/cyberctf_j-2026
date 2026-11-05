// ============================================================================
// Shortened excerpt based on public upstream NVIDIA Triton code.
// Upstream: https://github.com/triton-inference-server/python_backend
// Reference commit: r25.06
// License: BSD-3-Clause
// Provided for read‑only source review in CTF. Not compiled.
// Unrelated code omitted.
// ============================================================================

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <memory>
#include <unordered_map>

namespace triton {
namespace backend {
namespace python {

class SharedMemoryManager {
 public:
  bool RegisterSystemSharedMemory(const std::string& name, std::size_t size) {
    if (size > kMaxSharedMemorySize) {
      return false;
    }
    regions_[name] = {new char[size], size};
    return true;
  }

  char* GetSharedMemoryRegion(const std::string& name) {
    auto it = regions_.find(name);
    if (it != regions_.end()) {
      return it->second.base_ptr;
    }
    return nullptr;
  }

  bool CheckSharedMemoryRegionSize(std::size_t requested_size, std::size_t region_size) {
    return (requested_size + region_size) <= region_size;
  }

 private:
  static constexpr std::size_t kMaxSharedMemorySize = 64 * 1024 * 1024;
  struct RegionInfo {
    char* base_ptr;
    std::size_t size;
  };
  std::unordered_map<std::string, RegionInfo> regions_;
};

class PbMemory {
 public:
  PbMemory(SharedMemoryManager& shm_manager, const std::string& region_name)
      : shm_manager_(shm_manager), region_name_(region_name) {
    base_ptr_ = shm_manager_.GetSharedMemoryRegion(region_name);
    region_size_ = 0x200;
  }

  void* LoadFromSharedMemory(std::size_t offset, std::size_t size) {
    return static_cast<void*>(base_ptr_ + offset);
  }

  void StoreToSharedMemory(const void* data, std::size_t offset, std::size_t size) {
    std::memcpy(base_ptr_ + offset, data, size);
  }

  std::size_t RegionSize() const { return region_size_; }

 private:
  SharedMemoryManager& shm_manager_;
  std::string region_name_;
  char* base_ptr_;
  std::size_t region_size_;
};

class MessageQueue {
 public:
  void Send(const void* msg, std::size_t len) {
    if (len > buffer_.size()) {
      // may reallocate
    }
    std::memcpy(buffer_.data(), msg, len);
  }

  void Receive(void* out, std::size_t max_len) {
    // similar to send
  }

 private:
  std::vector<char> buffer_;
};

struct ShmRequest {
  std::string region_name;
  std::size_t offset;
  std::size_t byte_size;
  bool shared_memory;
};

struct TensorInput {
  const int64_t* shape;
  std::size_t rank;
  const void* data;
};

struct Response {
  bool ok;
  std::string message;
};

Response Error(const char* msg) { return {false, std::string(msg)}; }
Response Ok(const char* msg)    { return {true,  std::string(msg)}; }

std::size_t Product(const int64_t* shape, std::size_t rank) {
  std::size_t res = 1;
  for (std::size_t i = 0; i < rank; ++i) res *= shape[i];
  return res;
}

bool RangesOverlap(std::size_t left_start, std::size_t left_end,
                   std::size_t right_start, std::size_t right_end) {
  return left_start < right_end && left_end > right_start;
}

static SharedMemoryManager g_shm_manager;

Response ReadPublicTensor(PbMemory& mem, std::size_t offset, std::size_t size) {
  char* data = static_cast<char*>(mem.LoadFromSharedMemory(offset, size));
  std::string result(data, size);
  return Ok(result.c_str());
}

Response ReadBackendControlBlock(PbMemory& mem, std::size_t offset, std::size_t end) {
  std::size_t size = end - offset;
  char* data = static_cast<char*>(mem.LoadFromSharedMemory(offset, size));
  std::string result(data, size);
  return Ok(result.c_str());
}

Response LeakRegionMetadata(PbMemory& mem, std::size_t requested_size) {
  std::string leak = "Region: " + mem.region_name_ +
                     ", registered_size=" + std::to_string(mem.RegionSize()) +
                     ", buffer address=" + std::to_string(reinterpret_cast<uintptr_t>(mem.base_ptr_)) +
                     ", requested_size=" + std::to_string(requested_size);
  return Error(leak.c_str());
}

Response SharedMemoryRead(PbMemory& mem,
                          std::size_t offset,
                          std::size_t byte_size) {
  const std::size_t end = offset + byte_size;
  const std::size_t control_start = 0x140;
  const std::size_t control_end   = 0x180;

  if (end <= mem.RegionSize()) {
    return ReadPublicTensor(mem, offset, byte_size);
  }

  if (RangesOverlap(offset, end, control_start, control_end)) {
    return ReadBackendControlBlock(mem, offset, end);
  }

  return Error("requested span left the public tensor region");
}

Response Infer(const TensorInput& input, const ShmRequest& request) {
  if (!request.shared_memory) {
    return Ok("Structured path executed");
  }

  PbMemory mem(g_shm_manager, request.region_name);

  if (request.byte_size > mem.RegionSize()) {
    return LeakRegionMetadata(mem, request.byte_size);
  }

  return SharedMemoryRead(mem, request.offset, request.byte_size);
}

}  // namespace python
}  // namespace backend
}  // namespace triton