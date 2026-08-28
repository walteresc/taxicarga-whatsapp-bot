import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'

export const useInboxLayout = () => {
  const route = useRoute()

  const isInboxRoute = computed(() =>
    route.path.includes('bandeja-entrada'),
  )

  return {
    isInboxRoute,
  }
}
