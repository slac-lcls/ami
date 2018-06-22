//
//  key_value_store.hpp
//
//
//  Created by Heirich, Alan on 5/3/18.
//

#ifndef key_value_store_hpp
#define key_value_store_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "string_serdez.hpp"

#include <nlohmann/json.hpp>
// for convenience


class KeyValueStore : public StringSerdez {
  
public:
  KeyValueStore();
  virtual ~KeyValueStore();
  void put(std::string key, std::string value);
  std::string get(std::string key);

  using json = nlohmann::json;
  typedef unsigned long int IndexCoordinate;
  
private:
  IndexCoordinate keyToIndexCoordinate(std::string key);
  StringSerdez* mStringSerdez;
};

#endif /* key_value_store_hpp */
