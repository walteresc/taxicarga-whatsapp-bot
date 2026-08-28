import { ref, onMounted } from 'vue'

const isVerticalNavCollapsed = ref(false)

export function useVerticalNavCollapse() {
  const loadCollapsedState = () => {
    const saved = localStorage.getItem('crm-sidebar-collapsed')
    if (saved !== null) {
      isVerticalNavCollapsed.value = JSON.parse(saved)
    }
  }

  const toggleVerticalNav = () => {
    isVerticalNavCollapsed.value = !isVerticalNavCollapsed.value
    localStorage.setItem('crm-sidebar-collapsed', JSON.stringify(isVerticalNavCollapsed.value))

    // Apply class to layout wrapper
    const wrapper = document.querySelector('.layout-wrapper')
    if (wrapper) {
      if (isVerticalNavCollapsed.value) {
        wrapper.classList.add('layout-vertical-nav-collapsed')
      } else {
        wrapper.classList.remove('layout-vertical-nav-collapsed')
      }
    }
  }

  onMounted(() => {
    loadCollapsedState()


    // Apply initial state
    const wrapper = document.querySelector('.layout-wrapper')
    if (wrapper && isVerticalNavCollapsed.value) {
      wrapper.classList.add('layout-vertical-nav-collapsed')
    }
  })

  return {
    isVerticalNavCollapsed,
    toggleVerticalNav,
  }
}
