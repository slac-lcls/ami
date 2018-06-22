//
//  telemetry_store.hpp
//  
//
//  Created by Heirich, Alan on 5/5/18.
//

#ifndef telemetry_store_hpp
#define telemetry_store_hpp

#include <stdio.h>

#include "key_value_store.hpp"

class TelemetryStore : public KeyValueStore {
  
public:
  TelemetryStore();
  virtual ~TelemetryStore();
  
private:
};


#endif /* telemetry_store_hpp */
