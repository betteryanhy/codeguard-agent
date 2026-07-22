<template>
  <div class="skeleton-card">
    <!-- Stat skeleton: icon + 2 text lines -->
    <div v-if="type === 'stat'" class="skeleton-stat">
      <el-skeleton :rows="0" animated class="stat-skeleton">
        <template #template>
          <div class="stat-skeleton-inner">
            <el-skeleton-item variant="circle" class="stat-icon-sk" />
            <div class="stat-text-sk">
              <el-skeleton-item variant="text" class="w-20" />
              <el-skeleton-item variant="text" class="w-12" />
            </div>
          </div>
        </template>
      </el-skeleton>
    </div>

    <!-- Chart skeleton: rectangle area -->
    <div v-else-if="type === 'chart'" class="skeleton-chart">
      <el-skeleton :rows="0" animated>
        <template #template>
          <el-skeleton-item variant="rect" class="chart-rect" />
        </template>
      </el-skeleton>
    </div>

    <!-- Card skeleton: title + N content lines -->
    <div v-else-if="type === 'card'" class="skeleton-card-default">
      <el-skeleton :rows="rows" animated>
        <template #template>
          <el-skeleton-item variant="h3" class="card-title-sk" />
          <el-skeleton-item
            v-for="i in rows"
            :key="i"
            variant="p"
            :class="['card-line-sk', { 'w-8': i === rows }]"
          />
        </template>
      </el-skeleton>
    </div>

    <!-- Table skeleton: header + N data rows -->
    <div v-else-if="type === 'table'" class="skeleton-table">
      <el-skeleton :rows="0" animated>
        <template #template>
          <div class="table-skeleton">
            <div class="table-header-sk">
              <el-skeleton-item variant="text" class="th-sk" />
              <el-skeleton-item variant="text" class="th-sk" />
              <el-skeleton-item variant="text" class="th-sk th-last" />
            </div>
            <div v-for="i in rows" :key="i" class="table-row-sk">
              <el-skeleton-item variant="text" class="td-sk" />
              <el-skeleton-item variant="text" class="td-sk" />
              <el-skeleton-item variant="text" class="td-sk td-last" />
            </div>
          </div>
        </template>
      </el-skeleton>
    </div>
  </div>
</template>

<script setup>
defineProps({
  type: {
    type: String,
    default: 'card',
    validator: (v) => ['card', 'chart', 'table', 'stat'].includes(v),
  },
  rows: { type: Number, default: 3 },
})
</script>

<style scoped>
.skeleton-card {
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 10px;
  padding: 20px;
}

/* Stat */
.skeleton-stat {
  max-width: 260px;
}
.stat-skeleton-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon-sk {
  width: 48px !important;
  height: 48px !important;
  flex-shrink: 0;
}
.stat-text-sk {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.w-20 { width: 60%; display: block; }
.w-12 { width: 40%; display: block; }

/* Chart */
.chart-rect {
  width: 100%;
  height: 240px;
  display: block;
}

/* Card default */
.card-title-sk {
  width: 45%;
  height: 22px;
  margin-bottom: 16px;
  display: block;
}
.card-line-sk {
  width: 100%;
  height: 16px;
  margin-top: 12px;
  display: block;
}
.card-line-sk.w-8 {
  width: 60%;
}

/* Table */
.table-skeleton {
  display: flex;
  flex-direction: column;
}
.table-header-sk {
  display: flex;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 4px;
}
.th-sk {
  width: 20%;
  height: 18px;
  display: block;
}
.th-last {
  flex: 1;
}
.table-row-sk {
  display: flex;
  gap: 16px;
  padding: 10px 0;
}
.td-sk {
  width: 20%;
  height: 16px;
  display: block;
}
.td-last {
  flex: 1;
}
</style>
