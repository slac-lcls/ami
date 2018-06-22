//
//  control_store.hpp
//  
//
//  Created by Heirich, Alan on 5/5/18.
//

#ifndef control_store_hpp
#define control_store_hpp

#include <stdio.h>

#include "key_value_store.hpp"

class ControlStore : public KeyValueStore {
  
public:
  ControlStore();
  virtual ~ControlStore();
  
private:
};

#endif /* control_store_hpp */
