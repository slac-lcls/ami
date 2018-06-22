//
//  string_serdez.hpp
//  
//
//  Created by Heirich, Alan on 5/5/18.
//

#ifndef string_serdez_h
#define string_serdez_h

#include <string>
#include <string.h>

class StringSerdez {
public:
  typedef std::string* FIELD_TYPE;
  static const size_t MAX_SERIALIZED_SIZE = sizeof(std::string);
  
  static size_t serialized_size(const FIELD_TYPE& val) {
    return val->size() + 1;
  }
  
  static size_t serialize(const FIELD_TYPE& val, void *buffer) {
    memcpy(buffer, val->c_str(), val->size() + 1);
    return val->size() + 1;
  }
  
  static size_t deserialize(FIELD_TYPE& val, const void *buffer) {
    val = new std::string((const char*)buffer);
    return val->size() + 1;
  }
  
  static void destroy(FIELD_TYPE& val) {
    delete val;
  }
};


#endif /* string_serdez_h */
