//
//  toplevel.cc
//  
//
//  Created by Heirich, Alan on 5/3/18.
//

#include "toplevel.hpp"


// static members of TopLevelTask
const unsigned TopLevelTask::MAX_CLIENTS;
const unsigned TopLevelTask::MAX_INDEX_POINTS_PER_ENTITY;
TopLevelTask::TaskIdEnum TopLevelTask::mDataSource;
unsigned TopLevelTask::mNumWorkers;
unsigned TopLevelTask::mNumGraphManagers;
unsigned TopLevelTask::mNumRobustnessMonitors;
char* TopLevelTask::mFilePathBase;

FileDataSource TopLevelTask::mFileDataSource;
SharedMemoryDataSource TopLevelTask::mSharedMemoryDataSource;
Worker TopLevelTask::mWorker;
Collector TopLevelTask::mCollector;
GraphManager TopLevelTask::mGraphManager;
RobustnessMonitor TopLevelTask::mRobustnessMonitor;

IndexSpace TopLevelTask::mTelemetryIndexSpace;
FieldSpace TopLevelTask::mTelemetryFieldSpace;
LogicalRegion TopLevelTask::mTelemetryRegion;
LogicalPartition TopLevelTask::mTelemetryLogicalPartition;
std::vector<FieldID> TopLevelTask::mTelemetryPersistentFields;
std::vector<FieldID> TopLevelTask::mTelemetryShadowFields;

IndexSpace TopLevelTask::mResultIndexSpace;
FieldSpace TopLevelTask::mResultFieldSpace;
LogicalRegion TopLevelTask::mResultRegion;
LogicalPartition TopLevelTask::mResultLogicalPartition;
std::vector<FieldID> TopLevelTask::mResultPersistentFields;
std::vector<FieldID> TopLevelTask::mResultShadowFields;

IndexSpace TopLevelTask::mControlIndexSpace;
FieldSpace TopLevelTask::mControlFieldSpace;
LogicalRegion TopLevelTask::mControlRegion;
LogicalPartition TopLevelTask::mControlLogicalPartition;
std::vector<FieldID> TopLevelTask::mControlPersistentFields;
std::vector<FieldID> TopLevelTask::mControlShadowFields;


TopLevelTask::TopLevelTask(){
  mDataSource = FILE_DATA_SOURCE_TASK;
  mNumWorkers = mNumGraphManagers = mNumRobustnessMonitors = 1;
  collectEnvironmentVariables();
}


TopLevelTask::~TopLevelTask(){
}


void TopLevelTask::collectEnvironmentVariables() {
  mFilePathBase = std::getenv("AMI2_FILE_PATH_BASE");
}

void TopLevelTask::createTelemetryFieldSpace(Context ctx, Runtime* runtime,
                                             FieldSpace& fieldSpace,
                                             std::vector<FieldID>& persistentFields,
                                             std::vector<FieldID>& shadowFields) {
  fieldSpace = runtime->create_field_space(ctx);
  FieldAllocator allocator = runtime->create_field_allocator(ctx, fieldSpace);
  RegionFieldEnum fieldId;
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), TELEMETRY_TIMESTAMP);
  assert(fieldId == TELEMETRY_TIMESTAMP);
  persistentFields.push_back(TELEMETRY_TIMESTAMP);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), TELEMETRY_TIMESTAMP_);
  assert(fieldId == TELEMETRY_TIMESTAMP_);
  shadowFields.push_back(TELEMETRY_TIMESTAMP_);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), TELEMETRY_DATA);
  assert(fieldId == TELEMETRY_DATA);
  persistentFields.push_back(TELEMETRY_DATA);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), TELEMETRY_DATA_);
  assert(fieldId == TELEMETRY_DATA_);
  shadowFields.push_back(TELEMETRY_DATA_);
}


void TopLevelTask::createResultFieldSpace(Context ctx, Runtime* runtime,
                                          FieldSpace& fieldSpace,
                                          std::vector<FieldID>& persistentFields,
                                          std::vector<FieldID>& shadowFields) {
  fieldSpace = runtime->create_field_space(ctx);
  FieldAllocator allocator = runtime->create_field_allocator(ctx, fieldSpace);
  RegionFieldEnum fieldId;
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), RESULT_TIMESTAMP);
  assert(fieldId == RESULT_TIMESTAMP);
  persistentFields.push_back(RESULT_TIMESTAMP);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), RESULT_TIMESTAMP_);
  assert(fieldId == RESULT_TIMESTAMP_);
  shadowFields.push_back(RESULT_TIMESTAMP_);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), RESULT_DATA);
  assert(fieldId == RESULT_DATA);
  persistentFields.push_back(RESULT_DATA);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), RESULT_DATA_);
  assert(fieldId == RESULT_DATA_);
  shadowFields.push_back(RESULT_DATA_);
}


void TopLevelTask::createControlFieldSpace(Context ctx, Runtime* runtime,
                                           FieldSpace& fieldSpace,
                                           std::vector<FieldID>& persistentFields,
                                           std::vector<FieldID>& shadowFields) {
  fieldSpace = runtime->create_field_space(ctx);
  FieldAllocator allocator = runtime->create_field_allocator(ctx, fieldSpace);
  RegionFieldEnum fieldId;
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), CONTROL_TIMESTAMP);
  assert(fieldId == CONTROL_TIMESTAMP);
  persistentFields.push_back(CONTROL_TIMESTAMP);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), CONTROL_TIMESTAMP_);
  assert(fieldId == CONTROL_TIMESTAMP_);
  shadowFields.push_back(CONTROL_TIMESTAMP_);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), CONTROL_DATA);
  assert(fieldId == CONTROL_DATA);
  persistentFields.push_back(CONTROL_DATA);
  fieldId = (RegionFieldEnum)allocator.allocate_field(sizeof(int), CONTROL_DATA_);
  assert(fieldId == CONTROL_DATA_);
  shadowFields.push_back(CONTROL_DATA_);
}


void TopLevelTask::createLogicalRegionWithPartition(Context ctx, Runtime* runtime, std::string name,
                                                    unsigned numEntities,
                                                    void (*createFieldSpace)(Context ctx, Runtime* runtime, FieldSpace& fieldSpace,                                              std::vector<FieldID>& persistentFields, std::vector<FieldID>& shadowFields),
                                                    IndexSpace& regionIndexSpace,
                                                    FieldSpace& regionFieldSpace,
                                                    LogicalRegion& region,
                                                    LogicalPartition& regionPartition,
                                                    std::vector<FieldID>& regionPersistentFields,
                                                    std::vector<FieldID>& regionShadowFields
                                                    ) {
  Point<2> low = { 0, 0 };
  Point<2> high = { numEntities - 1, MAX_INDEX_POINTS_PER_ENTITY - 1 };
  Rect<2> regionRect(low, high);
  regionIndexSpace = runtime->create_index_space(ctx, regionRect);
  runtime->attach_name(regionIndexSpace, (name + "IndexSpace").c_str());
  createFieldSpace(ctx, runtime, regionFieldSpace, regionPersistentFields, regionShadowFields);
  runtime->attach_name(regionFieldSpace, (name + "FieldSpace").c_str());
  region = runtime->create_logical_region(ctx, regionIndexSpace, regionFieldSpace);
  runtime->attach_name(region, name.c_str());
  
}



void TopLevelTask::createTelemetryLogicalRegion(Context ctx, Runtime* runtime, unsigned numEntities) {
  
  createLogicalRegionWithPartition(ctx, runtime, std::string("telemetry"), numEntities,
                                   createTelemetryFieldSpace, mTelemetryIndexSpace,
                                   mTelemetryFieldSpace, mTelemetryRegion,
                                   mTelemetryLogicalPartition, mTelemetryPersistentFields, mTelemetryShadowFields);
}


void TopLevelTask::createResultLogicalRegion(Context ctx, Runtime* runtime, unsigned numEntities) {
  
  createLogicalRegionWithPartition(ctx, runtime, std::string("result"), numEntities,
                                   createResultFieldSpace, mResultIndexSpace,
                                   mResultFieldSpace, mResultRegion,
                                   mResultLogicalPartition, mResultPersistentFields,
                                   mResultShadowFields);
  
}


void TopLevelTask::createControlLogicalRegion(Context ctx, Runtime* runtime, unsigned numEntities) {
  
  createLogicalRegionWithPartition(ctx, runtime, std::string("control"), numEntities,
                                   createControlFieldSpace, mControlIndexSpace,
                                   mControlFieldSpace, mControlRegion,
                                   mControlLogicalPartition, mControlPersistentFields,
                                   mControlShadowFields);
  
}


void TopLevelTask::createLogicalRegions(Context ctx, Runtime* runtime) {
  unsigned numEntities = mNumWorkers + mNumGraphManagers + mNumRobustnessMonitors + MAX_CLIENTS;
  createTelemetryLogicalRegion(ctx, runtime, numEntities);
  createResultLogicalRegion(ctx, runtime, numEntities);
  createControlLogicalRegion(ctx, runtime, numEntities);
}


void TopLevelTask::launchTelemetryProcessingTasks(Context ctx, Runtime* runtime) {
  
  Rect<1> launchBounds(0, mNumWorkers - 1);
  ArgumentMap argMap;
  IndexTaskLauncher dataSourceLauncher(mDataSource, launchBounds, TaskArgument(NULL, 0), argMap);
  FutureMap dataSourceFutureMap = runtime->execute_index_space(ctx, dataSourceLauncher);
  ArgumentMap workerArgMap(dataSourceFutureMap);
  IndexTaskLauncher workerLauncher(WORKER_TASK, launchBounds, TaskArgument(NULL, 0), workerArgMap);
  FutureMap workerFutureMap = runtime->execute_index_space(ctx, workerLauncher);
  ArgumentMap collectorArgMap(workerFutureMap);
  IndexTaskLauncher collectorLauncher(COLLECTOR_TASK, launchBounds, TaskArgument(NULL, 0), collectorArgMap);
  FutureMap collectorFutureMap = runtime->execute_index_space(ctx, collectorLauncher);
  
}

void TopLevelTask::launchGraphManagerTask(Context ctx, Runtime* runtime) {
  
  Rect<1> launchBounds(0, mNumGraphManagers - 1);
  ArgumentMap argMap;
  IndexTaskLauncher graphManagerLauncher(GRAPH_MANAGER_TASK, launchBounds, TaskArgument(NULL, 0), argMap);
  FutureMap graphManagerFutureMap = runtime->execute_index_space(ctx, graphManagerLauncher);
  
}

bool TopLevelTask::timeToMonitor() {
  return true;//TODO
}

bool TopLevelTask::timeToPersist() {
  return true;//TODO
}

void TopLevelTask::launchRobustnessMonitorTask(Context ctx, Runtime* runtime) {
  
  Rect<1> launchBounds(0, mNumRobustnessMonitors - 1);
  ArgumentMap argMap;
  IndexTaskLauncher robustnessMonitorLauncher(ROBUSTNESS_MONITOR_TASK, launchBounds, TaskArgument(NULL, 0), argMap);
  FutureMap robustnessMonitorFutureMap = runtime->execute_index_space(ctx, robustnessMonitorLauncher);
  
}

void TopLevelTask::maybeOpenFileDataSource() {
  if(mFilePathBase != nullptr) {
    mFileDataSource.selectFileDataSource(mFilePathBase);
  }
}



void TopLevelTask::persistLogicalRegion(Context ctx, Runtime* runtime,
                                        LogicalRegion region,
                                        std::string name,
                                        std::vector<FieldID> persistentFields,
                                        std::vector<FieldID> shadowFields) {
  
  AttachLauncher attachLauncher(EXTERNAL_POSIX_FILE, region, region);
  attachLauncher.attach_file(name.c_str(), shadowFields, LEGION_FILE_CREATE);
  PhysicalRegion physicalRegion = runtime->attach_external_resource(ctx, attachLauncher);
  
  CopyLauncher copyLauncher;
  std::vector<FieldID>::iterator shadowIt = shadowFields.begin();
  std::vector<FieldID>::iterator persistentIt = persistentFields.begin();
  for( ; shadowIt != shadowFields.end(); shadowIt++, persistentIt++) {
    copyLauncher.add_copy_requirements(
                                       RegionRequirement(region, READ_ONLY, EXCLUSIVE, region).add_field(*persistentIt),
                                       RegionRequirement(region, READ_WRITE, EXCLUSIVE, region).add_field(*shadowIt)
                                       );
  }
  runtime->issue_copy_operation(ctx, copyLauncher);
  runtime->detach_external_resource(ctx, physicalRegion);
}

void TopLevelTask::persistTelemetryRegion(Context ctx, Runtime* runtime) {
  persistLogicalRegion(ctx, runtime, mTelemetryRegion, std::string("telemetry"),
                       mTelemetryPersistentFields,
                       mTelemetryShadowFields);
}

void TopLevelTask::persistResultRegion(Context ctx, Runtime* runtime) {
  persistLogicalRegion(ctx, runtime, mResultRegion, std::string("result"),
                       mResultPersistentFields,
                       mResultShadowFields);
}

void TopLevelTask::persistControlRegion(Context ctx, Runtime* runtime) {
  persistLogicalRegion(ctx, runtime, mControlRegion, std::string("control"),
                       mControlPersistentFields,
                       mControlShadowFields);
}

void TopLevelTask::persistLogicalRegions(Context ctx, Runtime* runtime) {
  persistTelemetryRegion(ctx, runtime);
  persistResultRegion(ctx, runtime);
  persistControlRegion(ctx, runtime);
}


void TopLevelTask::top_level_task(const Task* task,
                                  const std::vector<PhysicalRegion> &regions,
                                  Context ctx, Runtime* runtime) {
  
  createLogicalRegions(ctx, runtime);
  maybeOpenFileDataSource();
  
  do {
    
    launchTelemetryProcessingTasks(ctx, runtime);
    launchGraphManagerTask(ctx, runtime);
    
    if(timeToMonitor()) {
      launchRobustnessMonitorTask(ctx, runtime);
    }
    
    if(timeToPersist()) {
      persistLogicalRegions(ctx, runtime);
    }
    
  } while(true);
  
}





