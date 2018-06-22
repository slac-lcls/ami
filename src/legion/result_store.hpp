//
//  result_store.hpp
//  
//
//  Created by Heirich, Alan on 5/5/18.
//

#ifndef result_store_hpp
#define result_store_hpp

#include <stdio.h>

#include "key_value_store.hpp"

class ResultStore : public KeyValueStore {

public:
  ResultStore();
  virtual ~ResultStore();

private:
};

#endif /* result_store_hpp */
