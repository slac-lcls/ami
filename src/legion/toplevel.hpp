//
//  toplevel.hpp
//
//
//  Created by Heirich, Alan on 5/3/18.
//

#ifndef toplevel_hpp
#define toplevel_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "worker.hpp"
#include "shared_memory_data_source.hpp"
#include "file_data_source.hpp"
#include "graph_manager.hpp"
#include "robustness_monitor.hpp"
#include "control_store.hpp"
#include "robust_task.hpp"
#include "collector.hpp"



class TopLevelTask : public RobustTask {
public:
  enum TaskIdEnum {
    TOP_LEVEL_TASK,
    WORKER_TASK,
    COLLECTOR_TASK,
    SHARED_MEMORY_DATA_SOURCE_TASK,
    FILE_DATA_SOURCE_TASK,
    GRAPH_MANAGER_TASK,
    ROBUSTNESS_MONITOR_TASK
  };
  static const unsigned MAX_CLIENTS = 1024;
  static const unsigned MAX_INDEX_POINTS_PER_ENTITY = 128;
  
  enum RegionFieldEnum {
    TELEMETRY_TIMESTAMP,
    TELEMETRY_TIMESTAMP_,
    TELEMETRY_DATA,
    TELEMETRY_DATA_,
    
    RESULT_TIMESTAMP,
    RESULT_TIMESTAMP_,
    RESULT_DATA,
    RESULT_DATA_,
    
    CONTROL_TIMESTAMP,
    CONTROL_TIMESTAMP_,
    CONTROL_DATA,
    CONTROL_DATA_
  };
  
  
public:
  TopLevelTask();
  virtual ~TopLevelTask();
  static void top_level_task(const Task* task,
                             const std::vector<PhysicalRegion> &regions,
                             Context ctx, Runtime* runtime);
  static void collectEnvironmentVariables();
  static unsigned numWorkers() { return mNumWorkers; }
  static unsigned numGraphManagers() { return mNumGraphManagers; }
  static unsigned numRobustnessMonitors() { return mNumRobustnessMonitors; }
  
private:
  static TaskIdEnum mDataSource;
  static unsigned mNumWorkers;
  static unsigned mNumGraphManagers;
  static unsigned mNumRobustnessMonitors;
  static FileDataSource mFileDataSource;
  static SharedMemoryDataSource mSharedMemoryDataSource;
  static Worker mWorker;
  static Collector mCollector;
  static GraphManager mGraphManager;
  static RobustnessMonitor mRobustnessMonitor;
  static char* mFilePathBase;
  
  static IndexSpace mTelemetryIndexSpace;
  static FieldSpace mTelemetryFieldSpace;
  static LogicalRegion mTelemetryRegion;
  static LogicalPartition mTelemetryLogicalPartition;
  static std::vector<FieldID> mTelemetryPersistentFields;
  static std::vector<FieldID> mTelemetryShadowFields;

  static IndexSpace mResultIndexSpace;
  static FieldSpace mResultFieldSpace;
  static LogicalRegion mResultRegion;
  static LogicalPartition mResultLogicalPartition;
  static std::vector<FieldID> mResultPersistentFields;
  static std::vector<FieldID> mResultShadowFields;

  static IndexSpace mControlIndexSpace;
  static FieldSpace mControlFieldSpace;
  static LogicalRegion mControlRegion;
  static LogicalPartition mControlLogicalPartition;
  static std::vector<FieldID> mControlPersistentFields;
  static std::vector<FieldID> mControlShadowFields;

  static void createTelemetryFieldSpace(Context ctx, Runtime* runtime,
                                        FieldSpace& fieldSpace, std::vector<FieldID>& persistentFields, std::vector<FieldID>& shadowFields);
  static void createResultFieldSpace(Context ctx, Runtime* runtime,
                                     FieldSpace& fieldSpace, std::vector<FieldID>& persistentFields, std::vector<FieldID>& shadowFields);
  static void createControlFieldSpace(Context ctx, Runtime* runtime,
                                      FieldSpace& fieldSpace, std::vector<FieldID>& persistentFields, std::vector<FieldID>& shadowFields);
  static void createLogicalRegionWithPartition(Context ctx, Runtime* runtime,
                                               std::string name,
                                               unsigned numEntities,
                                               void (*createFieldSpace)(Context ctx, Runtime* runtime, FieldSpace& fieldSpace, std::vector<FieldID>& regionPersistentFields, std::vector<FieldID>& regionShadowFields),
                                               IndexSpace& regionIndexSpace,
                                               FieldSpace& regionFieldSpace,
                                               LogicalRegion& region,
                                               LogicalPartition& regionPartition,
                                               std::vector<FieldID>& regionPersistentFields,
                                               std::vector<FieldID>& regionShadowFields);
  static void createTelemetryLogicalRegion(Context ctx, Runtime* runtime, unsigned numEntities);
  static void createResultLogicalRegion(Context ctx, Runtime* runtime, unsigned numEntities);
  static void createControlLogicalRegion(Context ctx, Runtime* runtime, unsigned numEntities);
  static void createLogicalRegions(Context ctx, Runtime* runtime);
  static void launchTelemetryProcessingTasks(Context ctx, Runtime* runtime);
  static void launchGraphManagerTask(Context ctx, Runtime* runtime);
  static bool timeToMonitor();
  static bool timeToPersist();
  static void launchRobustnessMonitorTask(Context ctx, Runtime* runtime);
  static void persistLogicalRegion(Context ctx, Runtime* runtime,
                                   LogicalRegion region,
                                   std::string name,
                                   std::vector<FieldID> persistentFields,
                                   std::vector<FieldID> shadowFields);
  static void persistTelemetryRegion(Context ctx, Runtime* runtime);
  static void persistResultRegion(Context ctx, Runtime* runtime);
  static void persistControlRegion(Context ctx, Runtime* runtime);
  static void persistLogicalRegions(Context ctx, Runtime* runtime);
  static void maybeOpenFileDataSource();
  
};


#endif /* toplevel_hpp */
