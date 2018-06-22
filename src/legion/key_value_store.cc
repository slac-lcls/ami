//
//  key_value_store.cc
//
//
//  Created by Heirich, Alan on 5/3/18.
//

#include "key_value_store.hpp"




KeyValueStore::KeyValueStore() {
  mStringSerdez = new StringSerdez();
}

KeyValueStore::~KeyValueStore() {
  delete mStringSerdez;
}

void KeyValueStore::put(std::string key, std::string value) {
  
}

std::string KeyValueStore::get(std::string) {
  return "";
}


KeyValueStore::IndexCoordinate KeyValueStore::keyToIndexCoordinate(std::string key) {
  return 0;
}

